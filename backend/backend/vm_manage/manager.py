# coding: utf-8

# import threading
from itertools import chain

import time
import weakref
from redis import StrictRedis

from .models import VmDescriptor
from . import VmStates, KEY_VM_INSTANCE, KEY_VM_POOL

set_checking_state_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state ~= "got_ip" and old_state ~= "ready"  then
    return nil
else
    redis.call("HSET", KEYS[1], "state", "check_health")
    return "OK"
end
"""

acquire_vm_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state ~= "ready"  then
    return nil
else
    redis.call("HMSET", KEYS[1], "state", "in_use", "bound_to_user", ARGV[1])
    return "OK"
end
"""


class VmManager(object):

    def __init__(self, opts, callback, checker=None, spawner=None, terminator=None):
        """
        Build VM manager, can be used in two modes:
        - Daemon which control VMs lifecycle, requires params `spawner,terminator`
        - Client to acquire and release VM in builder process

        :param opts: Global backend configuration
        :type opts: Bunch

        :param callback: object with method `log(msg)`
        :param checker: object with method `check_health(ip) -> None or raise exception`
        :param spawner: object with method `spawn() -> IP or raise exception`
        :param terminator: object with safe method `terminate(ip, vm_name)`
        """
        self.opts = opts

        self.callback = weakref.proxy(callback)
        self.checker = checker
        self.spawner = spawner
        self.terminator = terminator

        self.lua_scripts = {}

    def post_init(self):
        # TODO: read redis host/post from opts
        kwargs = {}
        if hasattr(self.opts, "redis_db"):
            kwargs["db"] = self.opts.redis_db
        self.rc = StrictRedis(**kwargs)

        self.lua_scripts["set_checking_state"] = self.rc.register_script(set_checking_state_lua)
        self.lua_scripts["acquire_vm_lua"] = self.rc.register_script(acquire_vm_lua)

    def add_vm_to_pool(self, vm_ip, vm_name, group):
        vmd = VmDescriptor(vm_ip, vm_name, group, VmStates.GOT_IP)
        pipe = self.rc.pipeline()
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
                vmd.store_field(pipe, "last_modified", time.time())
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
        for vmd in chain(dirtied_by_user, clean_list):
            vm_key = KEY_VM_INSTANCE.format(vm_name=vmd.vm_name)
            if self.lua_scripts["acquire_vm_lua"](keys=[vm_key], args=[username]) == "OK":
                return vmd
        else:
            raise Exception("No VM are available, please wait in queue")


    def terminate_vm(self, vm_name):
        # todo: 1) set terminating state 2) notify builder process (if any registered) 3) invoke terminator
        raise NotImplementedError()

    def get_all_vm_in_group(self, group):
        vm_name_list = self.rc.smembers(KEY_VM_POOL.format(group=group))
        return [VmDescriptor.load(self.rc, vm_name) for vm_name in vm_name_list]

    def get_vm_by_name(self, vm_name):
        return VmDescriptor.load(self.rc, vm_name)



    # deamon part
    def remove_old_dirty_vms(self):
        # terminate vms bound_to user and time.time()
        pass

    def check_ready_vms(self):
        # for machines in state ready and time.time() - vm.last_health_check > threshold_health_check
        pass

    def spawn_if_required(self):
        # here we should provide some complex logic to
        # 1) rate-limit VM creation
        # 2) spawn new vms in advance fast enough
        pass

    def do_cycle(self):
        self.remove_old_dirty_vms()
        self.check_ready_vms()
        self.spawn_if_required()

    def run_daemon(self):
        if self.spawner is None or self.terminator is None:
            raise RuntimeError("provide Spawner and Terminator to run VmManager daemon")

        while True:
            time.sleep(5)
            self.do_cycle()
