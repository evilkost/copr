# coding: utf-8

# import threading
from itertools import chain
import json
from setproctitle import setproctitle

import time
import traceback
import weakref
from multiprocessing import Process
from redis import StrictRedis
from backend.helpers import get_redis_connection

from .models import VmDescriptor
from . import VmStates, KEY_VM_INSTANCE, KEY_VM_POOL, Thresholds, KEY_VM_GROUPS, PUBSUB_VM_TERMINATION, KEY_VM_POOL_INFO, \
    PUBSUB_SPAWNER

# KEYS [1]: VMD key
# ARGS: None
set_checking_state_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state ~= "got_ip" and old_state ~= "ready"  then
    return nil
else
    redis.call("HSET", KEYS[1], "state", "check_health")
    return "OK"
end
"""

# KEYS [1]: VMD key
# ARGS [1]: user to bound; [2] current timestamp for `in_use_since`
acquire_vm_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state ~= "ready"  then
    return nil
else
    redis.call("HMSET", KEYS[1], "state", "in_use", "bound_to_user", ARGV[1], "in_use_since", ARGV[2])
    return "OK"
end
"""

# KEYS [1]: VMD key
# ARGS [1] current timestamp for `last_release`
release_vm_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state ~= "in_use" then
    return nil
else
    redis.call("HMSET", KEYS[1], "state", "ready", "last_release", ARGV[1])
    redis.call("HDEL", KEYS[1], "in_use_since")
    return "OK"
end
"""


class VmManager(object):
    """
    VM manager, can be used in two modes:
    - Daemon which control VMs lifecycle, requires params `spawner,terminator`
    - Client to acquire and release VM in builder process

    :param opts: Global backend configuration
    :type opts: Bunch

    :param callback: object with method `log(msg)`
    :param checker: object with method `check_health(ip) -> None or raise exception`
    :param spawner: object with method `spawn() -> IP or raise exception`
    :param terminator: object with safe method `terminate(ip, vm_name)`
    """
    def __init__(self, opts, events, checker, spawner=None, terminator=None):

        self.opts = weakref.proxy(opts)
        self.events = events

        self.checker = checker
        self.spawner = spawner
        self.terminator = terminator

        self.lua_scripts = {}

        self.rc = None

    def log(self, msg):
        self.events.put({"when": time.time(), "who": "vm_manager", "what": msg})

    def post_init(self):
        # TODO: read redis host/post from opts
        self.rc = get_redis_connection(self.opts)
        self.lua_scripts["set_checking_state"] = self.rc.register_script(set_checking_state_lua)
        self.lua_scripts["acquire_vm"] = self.rc.register_script(acquire_vm_lua)
        self.lua_scripts["release_vm"] = self.rc.register_script(release_vm_lua)

    @property
    def vm_groups(self):
        return self.rc.smembers(KEY_VM_GROUPS)

    def add_vm_to_pool(self, vm_ip, vm_name, group):
        # print("\n ADD VM TO POOL")
        if self.rc.sismember(KEY_VM_POOL.format(group=group), vm_name):
            raise Exception("Can't add VM `{}` to the pool, such name already used".format(vm_name))

        vmd = VmDescriptor(vm_ip, vm_name, group, VmStates.GOT_IP)
        # print("VMD: {}".format(vmd))
        pipe = self.rc.pipeline()
        pipe.sadd(KEY_VM_GROUPS, group)
        pipe.sadd(KEY_VM_POOL.format(group=group), vm_name)
        pipe.hmset(KEY_VM_INSTANCE.format(vm_name=vm_name), vmd.to_dict())
        pipe.execute()
        self.log("registered new VM: {}".format(vmd))

    def do_vm_check(self, vm_name):
        # vm = self.get_vm_by_name(vm_name)
        vm_key = KEY_VM_INSTANCE.format(vm_name=vm_name)

        if self.lua_scripts["set_checking_state"](keys=[vm_key]) == "OK":
            # entered
            self.log("checking vm: {}".format(vm_name))
            vmd = self.get_vm_by_name(vm_name)
            try:
                self.checker.check_health(vmd.vm_ip)
                pipe = self.rc.pipeline()
                vmd.store_field(pipe, "last_health_check", time.time())
                vmd.store_field(pipe, "state", VmStates.READY)

                pipe.execute()

            except Exception as err:
                self.log("Health check failed: {}, going to terminate".format(err))
                self.terminate_vm(vm_name)

        else:
            self.log("failed to start vm check, wrong state")
            return False

    def acquire_vm(self, group, username):
        # TODO: reject request if user acquired #machines > threshold_vm_per_user
        vmd_list = self.get_all_vm_in_group(group)
        ready_vmd_list = [vmd for vmd in vmd_list if vmd.state == VmStates.READY]
        # trying to find VM used by this user
        dirtied_by_user = [vmd for vmd in ready_vmd_list if vmd.bound_to_user == username]
        clean_list = [vmd for vmd in ready_vmd_list if vmd.bound_to_user is None]
        all_vms = list(chain(dirtied_by_user, clean_list))

        for vmd in all_vms:
            vm_key = KEY_VM_INSTANCE.format(vm_name=vmd.vm_name)
            if self.lua_scripts["acquire_vm"](keys=[vm_key], args=[username, time.time()]) == "OK":
                return vmd
        else:
            raise Exception("No VM are available, please wait in queue")

    def release_vm(self, vm_name):
        # in_use -> ready
        vm_key = KEY_VM_INSTANCE.format(vm_name=vm_name)
        if not self.lua_scripts["release_vm"](keys=[vm_key], args=[time.time()]):
            raise Exception("VM not in in_use state")

    def terminate_vm(self, vm_name):
        vmd = self.get_vm_by_name(vm_name)
        vmd.store_field(self.rc, "state", VmStates.TERMINATING)
        self.rc.publish(PUBSUB_VM_TERMINATION.format(vm_name=vm_name), VmStates.TERMINATING)

        try:
            self.terminator.terminate(vm_ip=vmd.vm_ip, vm_name=vm_name, group=vmd.group)
        except Exception as err:
            self.log("Failed to terminate `{}` due to: {}".format(vm_name, err))
            return
        # make it safe and async
        vmd.store_field(self.rc, "state", VmStates.TERMINATED)
        self.remove_vm_from_pool(vm_name)

    def remove_vm_from_pool(self, vm_name):
        vmd = self.get_vm_by_name(vm_name)
        if vmd.get_field(self.rc, "state") != VmStates.TERMINATED:
            raise Exception("VM should have `terminated` state to be removable")
        pipe = self.rc.pipeline()
        pipe.srem(KEY_VM_POOL.format(group=vmd.group), vm_name)
        pipe.delete(KEY_VM_INSTANCE.format(vm_name=vm_name))
        pipe.execute()

    def get_all_vm_in_group(self, group):
        vm_name_list = self.rc.smembers(KEY_VM_POOL.format(group=group))
        return [VmDescriptor.load(self.rc, vm_name) for vm_name in vm_name_list]

    def get_vm_by_name(self, vm_name):
        """
        :rtype: VmDescriptor
        """
        return VmDescriptor.load(self.rc, vm_name)


class VmManagerDaemon(Process):
    def __init__(self, vm_manager):
        super(VmManagerDaemon, self).__init__(name="vm_manager")

        self.opts = vm_manager.opts
        self.vmm = vm_manager
        self.log = vm_manager.log

        self.kill_received = False

    def remove_old_dirty_vms(self):
        # terminate vms bound_to user and time.time() - vm.last_release_time > threshold_keep_vm_for_user_timeout
        #  or add field to VMD ot override common threshold
        pass

    def check_ready_vms(self):
        # for machines in state ready and time.time() - vm.last_health_check > threshold_health_check_period
        vmd_list = []
        # import ipdb; ipdb.set_trace()
        for group in self.vmm.vm_groups:
            sub_list = self.vmm.get_all_vm_in_group(group)
            vmd_list.extend(vmd for vmd in sub_list if vmd.state in [VmStates.READY, VmStates.GOT_IP])

        for vmd in vmd_list:
            last_health_check = vmd.get_field(self.vmm.rc, "last_health_check")
            if last_health_check:
                since_last_check = time.time() - float(last_health_check)
                if since_last_check < Thresholds.health_check_period:
                    continue
            self.vmm.do_vm_check(vmd.vm_name)

    def start_spawn_if_required(self):
        for group in range(self.opts.build_groups_count):
            max_vm_total = self.opts.build_groups[group]["max_vm_total"]
            if self.vmm.rc.scard(KEY_VM_POOL) >= max_vm_total:
                continue
            last_vm_spawn_start = self.vmm.rc.hget(KEY_VM_POOL_INFO.format(group=group), "last_vm_spawn_start")
            if last_vm_spawn_start:
                since_last_spawn = time.time() - float(last_vm_spawn_start)
                if since_last_spawn < Thresholds.vm_spawn_min_interval:
                    continue
            if len(self.vmm.spawner.child_processes) >= self.opts.build_groups[group]["max_spawn_processes"]:
                continue
            self.log("start spawning new VM")
            self.vmm.rc.hset(KEY_VM_POOL_INFO.format(group=group), "last_vm_spawn_start", time.time())
            self.vmm.spawner.start_spawn(group)

    def register_spawned_vms(self):
        empty_msg_counter = 3
        while True:
            raw = self.spawner_channel.get_message()
            if raw is None:
                empty_msg_counter -= 1
                time.sleep(0.001)  # TODO: fixme please: remove
                if empty_msg_counter < 0:
                    break
            else:
                if raw["type"] != "message":
                    continue

                msg = json.loads(raw["data"])
                # format {"group": 1, "vm_name": "builder 1245", "ip": 192.168.25.2}
                self.vmm.add_vm_to_pool(msg["ip"], msg["vm_name"], msg["group"])

    def subscribe_pubsub_channels(self):
        self.spawner_channel = self.vmm.rc.pubsub(ignore_subscribe_messages=True)
        self.spawner_channel.subscribe(PUBSUB_SPAWNER)
        #self.spawner_channel.get_message()
        #self.spawner_channel.get_message()
        self.log("Subscribed to spawns")

        self.terminator_channel = self.vmm.rc.pubsub(ignore_subscribe_messages=True)
        self.terminator_channel.subscribe(PUBSUB_VM_TERMINATION)
        #self.spawner_channel.get_message()
        #self.spawner_channel.get_message()
        self.log("Subscribed to terminations")

    def terminate_abandoned_vms(self):
        # If builder process forget about vm clean up, we should terminate it (more safe than marking it ready)
        # check by `in_use_since` > threshold_max_in_use_time, or add field to VMD which overrides this timeout
        # Also run terminate again for VM in `terminating` state with
        #   time.time() - terminating_since > threshold_terminating_timeout
        pass

    def do_cycle(self):
        self.log("starting do_cycle")
        # TODO: each check should be executed in threads ... and finish with join?
        self.terminate_abandoned_vms()
        self.remove_old_dirty_vms()
        self.check_ready_vms()
        self.start_spawn_if_required()

        self.register_spawned_vms()
        # self.check_vm_in_use() # detect broken VMS faster

    def start(self):
        if self.vmm.spawner is None or self.vmm.terminator is None or self.vmm.checker is None:
            raise RuntimeError("provide Spawner and Terminator to run VmManager daemon")

        setproctitle("vm_manager")

        self.kill_received = False
        self.subscribe_pubsub_channels()
        while True:
            time.sleep(Thresholds.cycle_timeout)
            try:
                self.do_cycle()
            except Exception as err:
                self.log("Unhandled error: {}, {}".format(err, traceback.format_exc()))
                #from celery.contrib import rdb; rdb.set_trace()
                #x = 2

    def terminate(self):
        self.kill_received = True
        # TODO: terminate VMs
