# coding: utf-8

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
import json

from multiprocessing import Process
import time
from setproctitle import setproctitle
import traceback
import sys
import psutil

from backend.constants import DEF_BUILD_TIMEOUT, JOB_GRAB_TASK_END_PUBSUB
from backend.helpers import format_tb
from backend.vm_manage import VmStates, Thresholds, KEY_VM_POOL_INFO
from backend.vm_manage.event_handle import EventHandler


class VmMaster(Process):
    """
    Spawns and terminate VM for builder process. Mainly wrapper for ..vm_manage package.

    :type vm_manager: backend.vm_manage.manager.VmManager
    """
    def __init__(self, vm_manager):
        super(VmMaster, self).__init__(name="vm_master")

        self.opts = vm_manager.opts
        self.vmm = vm_manager
        self.log = vm_manager.log

        self.kill_received = False

        self.spawned_handler = None

    def remove_old_dirty_vms(self):
        # terminate vms bound_to user and time.time() - vm.last_release_time > threshold_keep_vm_for_user_timeout
        #  or add field to VMD ot override common threshold
        ready_vmd_list = self.vmm.get_vm_by_group_and_state_list(None, [VmStates.READY])
        for vmd in ready_vmd_list:
            if vmd.get_field(self.vmm.rc, "bound_to_user") is not None:
                last_release = vmd.get_field(self.vmm.rc, "last_release")
                if last_release is None:
                    continue
                not_re_acquired_in = time.time() - float(last_release)
                if not_re_acquired_in > Thresholds.dirty_vm_terminating_timeout:
                    self.log("dirty VM `{}` not re-acquired in {}, terminating it"
                             .format(vmd.vm_name, not_re_acquired_in))
                    self.vmm.terminate_vm(vmd.vm_name, allowed_pre_state=VmStates.READY)

    def remove_vm_with_dead_builder(self):
        # check that process who acquired VMD stil exists, othrewise release VM
        in_use_vmd_list = self.vmm.get_vm_by_group_and_state_list(None, [VmStates.IN_USE])
        self.log("VM in use: {}".format(map(lambda x: (x.vm_name, x.state, getattr(x, "used_by_pid")), in_use_vmd_list)))
        for vmd in in_use_vmd_list:
            pid = vmd.get_field(self.vmm.rc, "used_by_pid")
            if pid is None:
                continue
            else:
                pid = int(pid)
                if not psutil.pid_exists(pid) or vmd.vm_name not in psutil.Process(pid).name:
                    self.log("Process `{}` not exists anymore, releasing VM: {} ".format(pid, str(vmd)))
                    self.vmm.release_vm(vmd.vm_name)

                    vmd_dict = vmd.to_dict()
                    if all(x in vmd_dict for x in ["build_id", "task_id", "chroot"]):
                        request = {
                            "action": "reschedule",
                            "build_id": vmd.build_id,
                            "task_id": vmd.task_id,
                            "chroot": vmd.chroot,
                        }

                        self.vmm.rc.publish(JOB_GRAB_TASK_END_PUBSUB, json.dumps(request))

    def check_vms_health(self):
        # for machines in state ready and time.time() - vm.last_health_check > threshold_health_check_period
        states_to_check = [VmStates.CHECK_HEALTH_FAILED, VmStates.READY,
                           VmStates.GOT_IP, VmStates.IN_USE]
        # vmd_list = [
        #     vmd for vmd
        #     in self.vmm.get_all_vm()
        #     if vmd.state in states_to_check
        # ]
        # # for group in self.vmm.vm_groups:
        # #     sub_list = self.vmm.get_all_vm_in_group(group)
        # #     vmd_list.extend(vmd for vmd in sub_list if vmd.state in states_to_check)

        for vmd in self.vmm.get_all_vm():
            if vmd.state not in states_to_check:
                continue

            last_health_check = vmd.get_field(self.vmm.rc, "last_health_check")
            if last_health_check:
                since_last_check = time.time() - float(last_health_check)
                if since_last_check < Thresholds.health_check_period:
                    continue
            self.vmm.do_vm_check(vmd.vm_name)

    def start_spawn_if_required(self):
        for group in range(self.opts.build_groups_count):
            max_vm_total = self.opts.build_groups[group]["max_vm_total"]
            active_vmd_list = self.vmm.get_vm_by_group_and_state_list(
                group, [VmStates.GOT_IP, VmStates.READY, VmStates.IN_USE, VmStates.CHECK_HEALTH])

            # self.log("active VM#: {}".format(map(lambda x: (x.vm_name, x.state), active_vmd_list)))
            if len(active_vmd_list) + self.vmm.spawner.children_number >= max_vm_total:
                continue
            last_vm_spawn_start = self.vmm.rc.hget(KEY_VM_POOL_INFO.format(group=group), "last_vm_spawn_start")
            if last_vm_spawn_start:
                since_last_spawn = time.time() - float(last_vm_spawn_start)
                if since_last_spawn < Thresholds.vm_spawn_min_interval:
                    self.log("time after previous spawn attempt < vm_spawn_min_interval")
                    continue

            if len(self.vmm.spawner.child_processes) >= self.opts.build_groups[group]["max_spawn_processes"]:
                self.log("max_spawn_processes reached")
                continue

            if len(self.vmm.get_all_vm_in_group(group)) >= self.opts.build_groups[group]["max_vm_total"]:
                self.log("fail save ALL VM >= max_vm_total reached")
                self.log("all VM#: {}".format(map(str, self.vmm.get_all_vm_in_group(group))))
                continue

            self.log("start spawning new VM for group: {}".format(self.opts.build_groups[group]["name"]))
            self.vmm.rc.hset(KEY_VM_POOL_INFO.format(group=group), "last_vm_spawn_start", time.time())
            try:
                self.vmm.spawner.start_spawn(group)
            except Exception as err:
                _, _, ex_tb = sys.exc_info()
                self.log("Error during spawn attempt: {} {}".format(err, format_tb(err, ex_tb)))

    def terminate_abandoned_vms(self):
        max_time = time.time() + DEF_BUILD_TIMEOUT * 2
        #for group in range(self.opts.build_groups_count):
        is_use_vmd_list = self.vmm.get_vm_by_group_and_state_list(None, [VmStates.IN_USE])

        # If builder process forget about vm clean up, we should terminate it (more safe than marking it ready)
        # check by `in_use_since` > threshold_max_in_use_time, or add field to VMD which overrides this timeout
        # Also run terminate again for VM in `terminating` state with
        #   time.time() - terminating_since > threshold_terminating_timeout
        pass

    def do_cycle(self):
        self.log("starting do_cycle")

        # TODO: each check should be executed in threads ... and finish with join?
        # self.terminate_abandoned_vms()
        self.remove_old_dirty_vms()
        self.check_vms_health()
        self.start_spawn_if_required()
        # self.remove_vm_with_dead_builder()

        self.vmm.checker.recycle()
        self.vmm.spawner.recycle()
        # self.vmm.terminator.recycle()

    def run(self):
        if self.vmm.spawner is None or self.vmm.terminator is None or self.vmm.checker is None:
            raise RuntimeError("provide Spawner and Terminator to run VmManager daemon")

        setproctitle("VM master")

        self.kill_received = False

        self.event_handler = EventHandler(self.vmm)
        self.event_handler.start()

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
        self.event_handler.terminate()
        self.event_handler.join()
        # TODO: terminate VMs
