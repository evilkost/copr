# coding: utf-8

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from collections import defaultdict
import json

from multiprocessing import Process
import time
from setproctitle import setproctitle
import traceback
import weakref

from requests import get, RequestException
from retask.task import Task
from retask.queue import Queue
import sys

from ..actions import Action
from backend.helpers import get_redis_connection, format_tb
from backend.vm_manage import VmStates, Thresholds, KEY_VM_POOL, KEY_VM_POOL_INFO, PUBSUB_MB, EventTopics
from backend.vm_manage.event_handle import EventHandler
from backend.vm_manage.manager import VmManager
from ..exceptions import CoprJobGrabError
from ..frontend import FrontendClient

from ..vm_manage.spawn import Spawner
from ..vm_manage.terminate import Terminator
from ..vm_manage.check import HealthChecker

#
# class EventCallback(object):
#     """
#     :param events: :py:class:`multiprocessing.Queue` to listen
#         for events from other backend components
#     """
#     def __init__(self, events):
#         self.events = events
#
#     def log(self, msg):
#         self.events.put({"when": time.time(), "who": "vm_master", "what": msg})

#
# handlers_map = {
#     EventTopics.HEALTH_CHECK: on_health_check_result,
#     EventTopics.VM_SPAWNED: on_vm_spawned,
#     EventTopics.VM_TERMINATION_REQUEST: on_vm_termination_request,
#     EventTopics.VM_TERMINATED: on_vm_termination_result,
# }
#
#
# def pubsub_handler(vmm):
#     """
#     Listens redis pubsub and perform requested actions.
#     Message payload is packed in json, it should be a dictionary
#         at the root level with reserved field `topic` which is required
#         for message routing
#     :type vmm: VmManager
#     """
#     setproctitle("pubsub handler")
#     channel = vmm.rc.pubsub(ignore_subscribe_messages=True)
#     channel.subscribe(PUBSUB_MB)
#     # TODO: check subscribe success
#     vmm.log("Spawned pubsub handler", who="pubsub handler")
#     for raw in channel.listen():
#         if raw is None:
#             continue
#         else:
#             if raw["type"] != "message":
#                 continue
#             try:
#                 msg = json.loads(raw["data"])
#
#                 if "topic" not in msg:
#                     raise Exception("Handler received msg without `topic` field, msg: {}".format(msg))
#                 topic = msg["topic"]
#                 if topic not in handlers_map:
#                     raise Exception("Handler received msg with unknown `topic` field, msg: {}".format(msg))
#
#                 handlers_map[topic](vmm, msg)
#
#             except Exception as err:
#                 _, _, ex_tb = sys.exc_info()
#                 vmm.log("Handler error: raw msg: {},  {} {}"
#                         .format(raw, err, format_tb(err, ex_tb)), who="event handler")


class VmMaster(Process):
    """
    Spawns and terminate VM for builder process. Mainly wrapper for ..vm_manage package.

    :param Bunch opts: backend config
    :param events: :py:class:`multiprocessing.Queue` to listen
        for events from other backend components
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
        pass

    def check_vms_health(self):
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
            active_vmd_list = self.vmm.get_vm_by_group_and_state_list(
                group, [VmStates.GOT_IP, VmStates.READY, VmStates.IN_USE])

            self.log("active VM#: {}".format(map(lambda x: (x.vm_name, x.state), active_vmd_list)))

            if len(active_vmd_list) + self.vmm.spawner.children_number >= max_vm_total:
                self.log("active VM#: {}, spawn processes #: {}"
                         .format(map(lambda x: (x.vm_name, x.state), active_vmd_list),
                                 self.vmm.spawner.children_number))
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

            self.log("start spawning new VM")
            self.vmm.rc.hset(KEY_VM_POOL_INFO.format(group=group), "last_vm_spawn_start", time.time())
            try:
                self.vmm.spawner.start_spawn(group)
            except Exception as err:
                _, _, ex_tb = sys.exc_info()
                self.log("Error during spawn attempt: {} {}".format(err, format_tb(err, ex_tb)))

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
        self.check_vms_health()
        self.start_spawn_if_required()

        self.vmm.checker.recycle()
        self.vmm.spawner.recycle()
        # self.vmm.terminator.recycle()

        # self.check_vm_in_use() # detect broken VMS faster

    def run(self):
        if self.vmm.spawner is None or self.vmm.terminator is None or self.vmm.checker is None:
            raise RuntimeError("provide Spawner and Terminator to run VmManager daemon")

        setproctitle("VM master")

        self.kill_received = False

        self.event_handler = EventHandler(self.vmm)
        self.event_handler.start()
        # self.pubsub_handler = Process(target=pubsub_handler, args=(self.vmm,))
        # self.pubsub_handler.start()

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
