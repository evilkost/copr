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
        self.event_handler = None

    def remove_old_dirty_vms(self):
        # terminate vms bound_to user and time.time() - vm.last_release_time > threshold_keep_vm_for_user_timeout
        #  or add field to VMD ot override common threshold
        for vmd in self.vmm.get_vm_by_group_and_state_list(None, [VmStates.READY]):
            if vmd.get_field(self.vmm.rc, "bound_to_user") is None:
                continue
            last_release = vmd.get_field(self.vmm.rc, "last_release")
            if last_release is None:
                continue
            not_re_acquired_in = time.time() - float(last_release)
            if not_re_acquired_in > Thresholds.dirty_vm_terminating_timeout:
                self.log("dirty VM `{}` not re-acquired in {}, terminating it"
                         .format(vmd.vm_name, not_re_acquired_in))
                self.vmm.start_vm_termination(vmd.vm_name, allowed_pre_state=VmStates.READY)

    def remove_vm_with_dead_builder(self):
        # check that process who acquired VMD still exists, otherwise release VM
        for vmd in self.vmm.get_vm_by_group_and_state_list(None, [VmStates.IN_USE]):
            pid = vmd.get_field(self.vmm.rc, "used_by_pid")
            if str(pid) != "None":
                pid = int(pid)
                if not psutil.pid_exists(pid) or vmd.vm_name not in psutil.Process(pid).name:
                    self.log("Process `{}` not exists anymore, releasing VM: {} ".format(pid, str(vmd)))
                    if self.vmm.release_vm(vmd.vm_name):
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

        for vmd in self.vmm.get_all_vm():
            if vmd.state in states_to_check:
                last_health_check = vmd.get_field(self.vmm.rc, "last_health_check")
                if not last_health_check or time.time() - float(last_health_check) > Thresholds.health_check_period:
                    self.vmm.start_vm_check(vmd.vm_name)

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

    def do_cycle(self):
        self.log("starting do_cycle")
        # TOOD: start_vm_check could potentially produce vmd with check state in case of server crash
        # so we need to restart check for VMD with health_check state + old age `last_health_check`

        # TODO: each check should be executed in threads ... and finish with join?
        # self.terminate_abandoned_vms()
        self.remove_old_dirty_vms()
        self.check_vms_health()
        self.start_spawn_if_required()
        # self.remove_vm_with_dead_builder()

        self.vmm.spawner.recycle()
        # self.vmm.terminator.recycle()

        # todo: self.terminate_old_unchecked_vms()

    def run(self):
        if self.vmm.spawner is None or self.vmm.terminator is None or self.vmm.checker is None:
            raise RuntimeError("provide Spawner and Terminator to run VmManager daemon")

        setproctitle("VM master")

        self.kill_received = False

        self.event_handler = EventHandler(self.vmm)
        self.event_handler.start()

        while not self.kill_received:
            time.sleep(Thresholds.cycle_timeout)
            try:
                self.do_cycle()
            except Exception as err:
                self.log("Unhandled error: {}, {}".format(err, traceback.format_exc()))
                #from celery.contrib import rdb; rdb.set_trace()
                #x = 2

    def terminate(self):
        self.kill_received = True
        if self.event_handler:
            self.event_handler.terminate()
            self.event_handler.join()

