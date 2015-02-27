# coding: utf-8

# import threading
from itertools import chain

import time
import weakref
from redis import StrictRedis

from .models import VmDescriptor
from . import VmStates, KEY_VM_INSTANCE, KEY_VM_POOL, Thresholds, KEY_VM_GROUPS, PUBSUB_VM_TERMINATION

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
    def __init__(self, opts, callback, checker=None, spawner=None, terminator=None):

        self.opts = opts

        self.callback = weakref.proxy(callback)
        self.checker = checker
        self.spawner = spawner
        self.terminator = terminator

        self.lua_scripts = {}

        self.rc = None

    def post_init(self):
        # TODO: read redis host/post from opts
        kwargs = {}
        if hasattr(self.opts, "redis_db"):
            kwargs["db"] = self.opts.redis_db
        self.rc = StrictRedis(**kwargs)

        self.lua_scripts["set_checking_state"] = self.rc.register_script(set_checking_state_lua)
        self.lua_scripts["acquire_vm"] = self.rc.register_script(acquire_vm_lua)
        self.lua_scripts["release_vm"] = self.rc.register_script(release_vm_lua)

    @property
    def vm_groups(self):
        return self.rc.smembers(KEY_VM_GROUPS)

    def add_vm_to_pool(self, vm_ip, vm_name, group):
        if self.rc.sismember(KEY_VM_POOL.format(group=group), vm_name):
            raise Exception("Can't add VM `{}` to the pool, such name already used".format(vm_name))

        vmd = VmDescriptor(vm_ip, vm_name, group, VmStates.GOT_IP)
        pipe = self.rc.pipeline()
        pipe.sadd(KEY_VM_GROUPS, group)
        pipe.sadd(KEY_VM_POOL.format(group=group), vm_name)
        pipe.hmset(KEY_VM_INSTANCE.format(vm_name=vm_name), vmd.to_dict())
        pipe.execute()

    def do_vm_check(self, vm_name):
        # vm = self.get_vm_by_name(vm_name)
        vm_key = KEY_VM_INSTANCE.format(vm_name=vm_name)

        if self.lua_scripts["set_checking_state"](keys=[vm_key]) == "OK":
            # entered
            vmd = self.get_vm_by_name(vm_name)
            try:
                self.checker.check_health(vmd.vm_ip)
                pipe = self.rc.pipeline()
                vmd.store_field(pipe, "last_health_check", time.time())
                vmd.store_field(pipe, "state", VmStates.READY)

                pipe.execute()

            except Exception as err:
                self.callback.log("Health check failed: {}, going to terminate".format(err))
                self.terminate_vm(vm_name)

        else:
            self.callback.log("failed to start vm check, wrong state")
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
        self.rc.publish(PUBSUB_VM_TERMINATION, vm_name)

        try:
            self.terminator.terminate(vm_ip=vmd.vm_ip, vm_name=vm_name, group=vmd.group)
        except Exception as err:
            self.callback.log("Failed to terminate `{}` due to: {}".format(vm_name, err))
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

#
#
#
    # deamon part
    def remove_old_dirty_vms(self):
        # terminate vms bound_to user and time.time() - vm.last_release_time > threshold_keep_vm_for_user_timeout
        #  or add field to VMD ot override common threshold
        pass

    def check_ready_vms(self):
        # for machines in state ready and time.time() - vm.last_health_check > threshold_health_check_period
        ready_vmd_list = []
        for group in self.vm_groups:
            vmd_list = self.get_all_vm_in_group(group)
            ready_vmd_list.extend(vmd for vmd in vmd_list if vmd.state == VmStates.READY)

        for vmd in ready_vmd_list:
            if time.time() - float(vmd.get_field(self.rc, "last_health_check")) < Thresholds.health_check_period:
                continue
            self.do_vm_check(vmd.vm_name)

    def spawn_if_required(self):
        # here we should provide some complex logic to
        # 1) rate-limit VM creation
        # 2) spawn new vms in advance fast enough
        pass

    def terminate_abandoned_vms(self):
        # If builder process forget about vm clean up, we should terminate it (more safe than marking it ready)
        # check by `in_use_since` > threshold_max_in_use_time, or add field to VMD which overrides this timeout
        # Also run terminate again for VM in `terminating` state with
        #   time.time() - terminating_since > threshold_terminating_timeout
        pass

    def do_cycle(self):
        # each check should be runnable in threads
        self.terminate_abandoned_vms()
        self.remove_old_dirty_vms()
        self.check_ready_vms()
        self.spawn_if_required()
        # self.check_vm_in_use() # detect broken VMS faster

    def run_daemon(self):
        if self.spawner is None or self.terminator is None:
            raise RuntimeError("provide Spawner and Terminator to run VmManager daemon")

        while True:
            time.sleep(Thresholds.cycle_timeout)
            self.do_cycle()
