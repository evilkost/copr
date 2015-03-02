# coding: utf-8

# import threading
from itertools import chain
import json
import time
import weakref

from backend.helpers import get_redis_connection
from .models import VmDescriptor
from . import VmStates, KEY_VM_INSTANCE, KEY_VM_POOL, KEY_VM_GROUPS, EventTopics, PUBSUB_MB

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

# KEYS [1]: VMD key
# ARGS [1] timestamp for `terminating_since`
terminate_vm_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state == "terminating" then
    return nil
else
    redis.call("HMSET", KEYS[1], "state", "terminating", "terminating_since", ARGV[1])
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
    def __init__(self, opts, events, checker=None, spawner=None, terminator=None):

        self.opts = weakref.proxy(opts)
        self.events = events

        self.checker = checker
        self.spawner = spawner
        self.terminator = terminator

        self.lua_scripts = {}

        self.rc = None

    def log(self, msg, who=None):
        self.events.put({"when": time.time(), "who": who or"vm_manager", "what": msg})

    def post_init(self):
        # TODO: read redis host/post from opts
        self.rc = get_redis_connection(self.opts)
        self.lua_scripts["set_checking_state"] = self.rc.register_script(set_checking_state_lua)
        self.lua_scripts["acquire_vm"] = self.rc.register_script(acquire_vm_lua)
        self.lua_scripts["release_vm"] = self.rc.register_script(release_vm_lua)
        self.lua_scripts["terminate_vm"] = self.rc.register_script(terminate_vm_lua)

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
                pipe = self.rc.pipeline()
                vmd.store_field(pipe, "last_health_check", time.time())
                vmd.store_field(pipe, "state", VmStates.READY)
                pipe.execute()
                self.checker.run_check_health(vmd.vm_name, vmd.vm_ip)

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
        """
        Initiate VM termination process
        """
        vmd = self.get_vm_by_name(vm_name)
        vm_key = KEY_VM_INSTANCE.format(vm_name=vm_name)
        if self.lua_scripts["terminate_vm"](keys=[vm_key], args=[time.time()]) == "OK":
            msg = {
                "group": vmd.group,
                "vm_ip": vmd.vm_ip,
                "vm_name": vmd.vm_name,
                "topic": EventTopics.VM_TERMINATION_REQUEST
            }
            self.rc.publish(PUBSUB_MB, json.dumps(msg))
            self.log("VM {} queued for termination".format(vmd))
            # TODO: Inform builder process if vmd has field `builder_pid` (or should it listen PUBSUB_TERMINATION ? )
        else:
            self.log("VM `{}` is already in terminating state, skipping ".format(vm_name))

    def remove_vm_from_pool(self, vm_name):
        """
        Backend forgets about VM after this method
        """
        vmd = self.get_vm_by_name(vm_name)
        if vmd.get_field(self.rc, "state") != VmStates.TERMINATING:
            raise Exception("VM should have `terminating` state to be removable")
        pipe = self.rc.pipeline()
        pipe.srem(KEY_VM_POOL.format(group=vmd.group), vm_name)
        pipe.delete(KEY_VM_INSTANCE.format(vm_name=vm_name))
        pipe.execute()
        self.log("removed vm `{}` from pool".format(vm_name))

    def get_all_vm_in_group(self, group):
        vm_name_list = self.rc.smembers(KEY_VM_POOL.format(group=group))
        return [VmDescriptor.load(self.rc, vm_name) for vm_name in vm_name_list]

    def get_vm_by_name(self, vm_name):
        """
        :rtype: VmDescriptor
        """
        return VmDescriptor.load(self.rc, vm_name)

    def get_vm_by_group_and_state_list(self, group, state_list):
        states = set(state_list)
        vmd_list = self.get_all_vm_in_group(group)
        return [vmd for vmd in vmd_list
                if int(vmd.group) == int(group) and vmd.state in states]


