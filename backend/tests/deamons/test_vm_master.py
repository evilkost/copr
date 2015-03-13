# coding: utf-8

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import

import copy

from collections import defaultdict
import json
import types
from bunch import Bunch
import time
from multiprocessing import Queue
from backend import exceptions
from backend.constants import JOB_GRAB_TASK_END_PUBSUB
from backend.exceptions import MockRemoteError, CoprSignError, BuilderError, VmError

import tempfile
import shutil
import os

import six
from backend.helpers import get_redis_connection
from backend.vm_manage import VmStates, Thresholds, KEY_VM_POOL, PUBSUB_VM_TERMINATION
from backend.vm_manage.check import HealthChecker
from backend.vm_manage.manager import VmManager
from backend.daemons.vm_master import VmMaster
from backend.vm_manage.models import VmDescriptor

if six.PY3:
    from unittest import mock
    from unittest.mock import patch, MagicMock
else:
    import mock
    from mock import patch, MagicMock

import pytest

from backend.mockremote import MockRemote, get_target_dir
from backend.mockremote.callback import DefaultCallBack
from backend.job import BuildJob


"""
REQUIRES RUNNING REDIS
TODO: look if https://github.com/locationlabs/mockredis can be used
"""

MODULE_REF = "backend.daemons.vm_master"

@pytest.yield_fixture
def mc_time():
    with mock.patch("{}.time".format(MODULE_REF)) as handle:
        yield handle

@pytest.yield_fixture
def mc_psutil():
    with mock.patch("{}.psutil".format(MODULE_REF)) as handle:
        yield handle

@pytest.yield_fixture
def mc_setproctitle():
    with mock.patch("{}.setproctitle".format(MODULE_REF)) as handle:
        yield handle


# @pytest.yield_fixture
# def mc_time_vmm():
#     with mock.patch("backend.vm_manage.manager.time") as handle:
#         yield handle


class TestCallback(object):
    def log(self, msg):
        print(msg)


class TestVmMaster(object):

    def setup_method(self, method):
        self.opts = Bunch(
            redis_db=9,
            ssh=Bunch(
                transport="ssh"
            ),
            build_groups_count=2,
            build_groups={
                0: {
                    "name": "base",
                    "archs": ["i386", "x86_64"]
                },
                1: {
                    "name": "arm",
                    "archs": ["armV7"]
                }
            },

            fedmsg_enabled=False,
            sleeptime=0.1,
        )
        self.queue = Queue()

        self.vm_ip = "127.0.0.1"
        self.vm_name = "localhost"
        self.group = 0
        self.username = "bob"

        self.rc = get_redis_connection(self.opts)
        self.ps = None
        self.log_msg_list = []

        self.callback = TestCallback()
        # checker = HealthChecker(self.opts, self.callback)
        self.checker = MagicMock()
        self.spawner = MagicMock()
        self.terminator = MagicMock()

        self.queue = Queue()
        self.vmm = VmManager(self.opts, self.queue,
                             checker=self.checker,
                             spawner=self.spawner,
                             terminator=self.terminator)
        self.vmm.post_init()

        self.event_handler = MagicMock()
        self.vm_master = VmMaster(self.vmm)
        self.vm_master.event_handler = MagicMock()
        self.pid = 12345

    def teardown_method(self, method):
        keys = self.vmm.rc.keys("*")
        if keys:
            self.vmm.rc.delete(*keys)

    @pytest.fixture
    def add_vmd(self):
        self.vmd_a1 = self.vmm.add_vm_to_pool(self.vm_ip, "a1", 0)
        self.vmd_a2 = self.vmm.add_vm_to_pool(self.vm_ip, "a2", 0)
        self.vmd_a3 = self.vmm.add_vm_to_pool(self.vm_ip, "a3", 0)
        self.vmd_b1 = self.vmm.add_vm_to_pool(self.vm_ip, "b1", 1)
        self.vmd_b2 = self.vmm.add_vm_to_pool(self.vm_ip, "b2", 1)
        self.vmd_b3 = self.vmm.add_vm_to_pool(self.vm_ip, "b3", 1)

    def rcv_from_ps_message_bus(self):
        # don't forget to subscribe self.ps
        rcv_msg_list = []
        for i in range(10):
            msg = self.ps.get_message()
            if msg:
                rcv_msg_list.append(msg)
            time.sleep(0.01)
        return rcv_msg_list

    def test_pass(self, add_vmd):
        pass

    def test_remove_old_dirty_vms(self, mc_time, add_vmd):
        # pass
        self.vmm.start_vm_termination = types.MethodType(MagicMock(), self.vmm)
        # VM in ready state, with not empty bount_to_user and (NOW - last_release) > threshold
        #   should be terminated
        for vmd in [self.vmd_a1, self.vmd_a2, self.vmd_b1, self.vmd_b2]:
            vmd.store_field(self.rc, "state", VmStates.READY)

        for vmd in [self.vmd_a1, self.vmd_a2, self.vmd_b1]:
            vmd.store_field(self.rc, "last_release", 0)

        for vmd in [self.vmd_a1, self.vmd_b1, self.vmd_b2]:
            vmd.store_field(self.rc, "bound_to_user", "user")

        for vmd in [self.vmd_a3, self.vmd_b3]:
            vmd.store_field(self.rc, "state", VmStates.IN_USE)

        mc_time.time.return_value = 1
        # no vm terminated
        self.vm_master.remove_old_dirty_vms()
        assert not self.vmm.start_vm_termination.called

        mc_time.time.return_value = Thresholds.dirty_vm_terminating_timeout + 1
        # only "a1" and "b1" should be terminated
        self.vm_master.remove_old_dirty_vms()
        assert self.vmm.start_vm_termination.called
        terminated_names = set([call[0][1] for call
                               in self.vmm.start_vm_termination.call_args_list])
        assert set(["a1", "b1"]) == terminated_names

    def test_remove_vm_with_dead_builder(self, mc_time, add_vmd, mc_psutil):
        self.vmm.release_vm = types.MethodType(MagicMock(), self.vmm)

        for idx, vmd in enumerate([self.vmd_a1, self.vmd_a2,
                                   self.vmd_b1, self.vmd_b2, self.vmd_b3]):
            vmd.store_field(self.rc, "state", VmStates.IN_USE)
            vmd.store_field(self.rc, "chroot", "fedora-20-x86_64")
            vmd.store_field(self.rc, "task_id", "{}-fedora-20-x86_64".format(idx + 1))
            vmd.store_field(self.rc, "build_id", idx + 1)

        self.rc.hdel(self.vmd_b3.vm_key, "chroot")

        for idx, vmd in enumerate([self.vmd_a1, self.vmd_a2, self.vmd_b2, self.vmd_b3]):
            vmd.store_field(self.rc, "used_by_pid", idx + 1)

        for vmd in [self.vmd_a3, self.vmd_a3]:
            vmd.store_field(self.rc, "state", VmStates.READY)

        def mc_psutil_process(pid):
            p = MagicMock()
            mapping = {
                "1": "a1",
                "2": "a2",
                "3": "b1",
                "4": "None",
                "5": "None",
            }
            p.name = "builder vm_name={} suffix".format(mapping.get(str(pid)))
            return p

        def mc_psutil_pid_exists(pid):
            if str(pid) in ["1", "4"]:
                return True

            return False

        mc_psutil.Process.side_effect = mc_psutil_process
        mc_psutil.pid_exists.side_effect = mc_psutil_pid_exists

        self.ps = self.vmm.rc.pubsub(ignore_subscribe_messages=True)
        self.ps.subscribe(JOB_GRAB_TASK_END_PUBSUB)
        self.vm_master.remove_vm_with_dead_builder()

        msg_list = self.rcv_from_ps_message_bus()

        assert set(["2", "4"]) == set([json.loads(m["data"])["build_id"] for m in msg_list])

    def test_check_vms_health(self, mc_time, add_vmd):
        self.vmm.start_vm_check = types.MethodType(MagicMock(), self.vmm)
        for vmd in [self.vmd_a1, self.vmd_a2, self.vmd_a3, self.vmd_b1, self.vmd_b2, self.vmd_b3]:
            vmd.store_field(self.rc, "last_health_check", 0)

        self.vmd_a1.store_field(self.rc, "state", VmStates.IN_USE)
        self.vmd_a2.store_field(self.rc, "state", VmStates.CHECK_HEALTH)
        self.vmd_a3.store_field(self.rc, "state", VmStates.CHECK_HEALTH_FAILED)
        self.vmd_b1.store_field(self.rc, "state", VmStates.GOT_IP)
        self.vmd_b2.store_field(self.rc, "state", VmStates.READY)
        self.vmd_b3.store_field(self.rc, "state", VmStates.TERMINATING)

        mc_time.time.return_value = 1
        self.vm_master.check_vms_health()
        assert not self.vmm.start_vm_check.called

        mc_time.time.return_value = 1 + Thresholds.health_check_period
        self.vm_master.check_vms_health()
        to_check = set(call[0][1] for call in self.vmm.start_vm_check.call_args_list)
        assert set(['a1', 'a3', 'b1', 'b2']) == to_check

        self.vmm.start_vm_check.reset_mock()
        for vmd in [self.vmd_a1, self.vmd_a2, self.vmd_a3, self.vmd_b1, self.vmd_b2, self.vmd_b3]:
            self.rc.hdel(self.vmd_a3.vm_key, "last_health_check")
        self.vm_master.check_vms_health()
        to_check = set(call[0][1] for call in self.vmm.start_vm_check.call_args_list)
        assert set(['a1', 'a3', 'b1', 'b2']) == to_check

    def test_finalize_long_health_checks(self, mc_time, add_vmd):

        mc_time.time.return_value = 0
        self.vmd_a1.store_field(self.rc, "state", VmStates.IN_USE)
        self.vmd_a2.store_field(self.rc, "state", VmStates.CHECK_HEALTH)
        self.vmd_a3.store_field(self.rc, "state", VmStates.CHECK_HEALTH)

        self.vmd_a2.store_field(self.rc, "last_health_check", 0)
        self.vmd_a3.store_field(self.rc, "last_health_check", Thresholds.health_check_max_time + 10 )

        mc_time.time.return_value = Thresholds.health_check_max_time + 11

        self.vmm.mark_vm_check_failed = MagicMock()
        self.vm_master.finalize_long_health_checks()
        assert self.vmm.mark_vm_check_failed.called_once
        assert self.vmm.mark_vm_check_failed.call_args[0][0] == "a2"





    def test_run_undefined_helpers(self, mc_setproctitle):
        for target in ["spawner", "terminator", "checker"]:
            setattr(self.vmm, target, None)
            with pytest.raises(RuntimeError):
                self.vm_master.run()

            setattr(self.vmm, target, MagicMock())

            assert not mc_setproctitle.called

    def test_dummy_run(self, mc_time, mc_setproctitle):
        mc_do_cycle = MagicMock()
        mc_do_cycle.side_effect = [
            VmError("FooBar"),
            None
        ]
        self.vm_master.do_cycle = types.MethodType(mc_do_cycle, self.vm_master)

        self.stage = 0
        def on_sleep(*args, **kwargs):
            self.stage += 1
            if self.stage == 1:
                pass
            elif self.stage >= 2:
                self.vm_master.kill_received = True
        mc_time.sleep.side_effect = on_sleep
        with mock.patch("{}.EventHandler".format(MODULE_REF)) as mc_event_handler:

            self.vm_master.run()

            assert mc_event_handler.called
            assert mc_event_handler.return_value.start.called

        err_log = self.queue.get(timeout=1)
        assert err_log is not None
        assert "Unhandled error:" in err_log["what"]

    def test_dummy_terminate(self):
        self.vm_master.terminate()
        assert self.vm_master.kill_received
        assert self.vm_master.event_handler.terminate.called

    def test_dummy_do_cycle(self):
        self.vm_master.remove_old_dirty_vms = types.MethodType(MagicMock(), self.vm_master)
        self.vm_master.check_vms_health = types.MethodType(MagicMock(), self.vm_master)
        self.vm_master.start_spawn_if_required = types.MethodType(MagicMock(), self.vm_master)
        # self.vm_master.remove_old_dirty_vms = types(MagicMock, self.vm_master)

        self.vm_master.do_cycle()

        assert self.vm_master.remove_old_dirty_vms.called
        assert self.vm_master.check_vms_health.called
        assert self.vm_master.start_spawn_if_required.called

        assert self.vmm.spawner.recycle.called

