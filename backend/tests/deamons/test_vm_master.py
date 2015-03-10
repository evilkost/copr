# coding: utf-8

import copy

from collections import defaultdict
import json
import types
from bunch import Bunch
import time
from multiprocessing import Queue
from backend import exceptions
from backend.exceptions import MockRemoteError, CoprSignError, BuilderError

import tempfile
import shutil
import os

import six
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

@pytest.yield_fixture
def mc_time():
    with mock.patch("backend.daemons.vm_master.time") as handle:
        yield handle

@pytest.yield_fixture
def mc_time_vmm():
    with mock.patch("backend.vm_manage.manager.time") as handle:
        yield handle


class TestCallback(object):
    def log(self, msg):
        print(msg)


class TestVmMaster(object):

    def setup_method(self, method):
        self.opts = Bunch(
            redis_db=9,
            ssh=Bunch(
                transport="ssh"
            )
        )
        self.callback = TestCallback()

        self.checker = MagicMock()
        self.spawner = MagicMock()
        self.terminator = MagicMock()

        self.queue = Queue()
        self.test_vmm = VmManager(self.opts, self.queue,
                                         checker=self.checker,
                                         spawner=self.spawner,
                                         terminator=self.terminator)
        self.test_vmm.post_init()

        self.vm_master = VmMaster(self.test_vmm)

        self.vm_ip = "127.0.0.1"
        self.vm_name = "localhost"
        self.group = "x86"
        self.username = "bob"

    def teardown_method(self, method):
        keys = self.test_vmm.rc.keys("*")
        if keys:
            self.test_vmm.rc.delete(*keys)

    def test_check_ready_vms_time(self, mc_time, mc_time_vmm):
        self.checker.check_health.return_value = None

        mc_time_vmm.time.return_value = mc_time.time.return_value = 1
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.start_vm_check(self.vm_name)
        self.test_vmm.add_vm_to_pool(self.vm_ip, "alternative", self.group)

        mc_time_vmm.time.return_value = mc_time.time.return_value = int(0.7 * Thresholds.health_check_period)
        self.test_vmm.start_vm_check("alternative")

        mc_time_vmm.time.return_value = mc_time.time.return_value = 1 + Thresholds.health_check_period
        self.checker.check_health.reset_mock()
        assert not self.checker.check_health.called
        mc_do_vm_check = MagicMock()
        self.test_vmm.start_vm_check = types.MethodType(mc_do_vm_check, self.test_vmm)
        assert not mc_do_vm_check.called

        self.vm_master.check_vms_health()

        assert mc_do_vm_check.called
        print(">> {}".format(mc_do_vm_check.call_args_list))
        assert not any(call_args[0][1] == "alternative" for call_args in mc_do_vm_check.call_args_list)

        mc_time_vmm.time.return_value = mc_time.time.return_value = 1 + Thresholds.health_check_period * 2
        self.vm_master.check_vms_health()
        assert any(call_args[0][1] == "alternative" for call_args in mc_do_vm_check.call_args_list)
