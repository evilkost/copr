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
from backend.vm_manage import VmStates, Thresholds, KEY_VM_POOL, PUBSUB_VM_TERMINATION, PUBSUB_SPAWNER
from backend.vm_manage.check import HealthChecker
from backend.vm_manage.manager import VmManager, VmManagerDaemon
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
    with mock.patch("backend.vm_manage.manager.time") as handle:
        yield handle


class TestCallback(object):
    def log(self, msg):
        print(msg)


class TestManager(object):

    def setup_method(self, method):
        self.opts = Bunch(
            redis_db=9,
            ssh=Bunch(
                transport="ssh"
            )
        )
        self.callback = TestCallback()
        # checker = HealthChecker(self.opts, self.callback)
        self.checker = MagicMock()
        self.spawner = MagicMock()
        self.terminator = MagicMock()

        self.queue = Queue()
        self.test_vmm = VmManager(self.opts, self.queue,
                                         checker=self.checker,
                                         spawner=self.spawner,
                                         terminator=self.terminator)
        self.test_vmm.post_init()

        self.vm_daemon = VmManagerDaemon(self.test_vmm)

        self.vm_ip = "127.0.0.1"
        self.vm_name = "localhost"
        self.group = "x86"
        self.username = "bob"

    def teardown_method(self, method):
        keys = self.test_vmm.rc.keys("*")
        if keys:
            self.test_vmm.rc.delete(*keys)

    def test_add_vm_to_pool(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)

        vm_list = self.test_vmm.get_all_vm_in_group(self.group)

        vm = self.test_vmm.get_vm_by_name(self.vm_name)
        assert len(vm_list) == 1
        assert vm_list[0].__dict__ == vm.__dict__
        assert self.group in self.test_vmm.vm_groups
        assert len(self.test_vmm.vm_groups) == 1

        with pytest.raises(Exception):
            self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)

    def test_check_vm(self, capsys):
        self.checker.check_health.return_value = None

        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.do_vm_check(self.vm_name)
        vmd = self.test_vmm.get_vm_by_name(self.vm_name)
        assert vmd.get_field(self.test_vmm.rc, "state") == VmStates.READY

        self.test_vmm.do_vm_check(self.vm_name)
        assert vmd.get_field(self.test_vmm.rc, "state") == VmStates.READY

        vmd.store_field(self.test_vmm.rc, "bound_to_user", "bob")
        self.test_vmm.do_vm_check(self.vm_name)
        assert vmd.get_field(self.test_vmm.rc, "state") == VmStates.READY

        self.checker.check_health.side_effect = exceptions.BuilderTimeOutError("foobar")
        # with pytest.raises(Exception):
        self.test_vmm.terminate_vm = types.MethodType(MagicMock(), self.test_vmm)
        self.test_vmm.do_vm_check(self.vm_name)
        assert self.test_vmm.terminate_vm.called

        vmd.store_field(self.test_vmm.rc, "state", VmStates.IN_USE)
        # should ignore
        self.test_vmm.do_vm_check(self.vm_name)

        out, err = capsys.readouterr()

    def test_acquire_vm(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.add_vm_to_pool(self.vm_ip, "alternative", self.group)
        self.test_vmm.do_vm_check(self.vm_name)
        self.test_vmm.do_vm_check("alternative")
        self.test_vmm.get_vm_by_name("alternative").store_field(self.test_vmm.rc, "bound_to_user", self.username)

        vmd_got_first = self.test_vmm.acquire_vm(group=self.group, username=self.username)
        assert vmd_got_first.vm_name == "alternative"
        vmd_got_second = self.test_vmm.acquire_vm(group=self.group, username=self.username)
        assert vmd_got_second.vm_name == self.vm_name
        
        with pytest.raises(Exception):
            self.test_vmm.acquire_vm(group=self.group, username=self.username)

    def test_acquire_only_ready_state(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        for state in [VmStates.IN_USE, VmStates.GOT_IP, VmStates.CHECK_HEALH,
                      VmStates.TERMINATING, VmStates.TERMINATED]:
            self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "state", state)
            with pytest.raises(Exception):
                self.test_vmm.acquire_vm(group=self.group, username=self.username)

    def test_acquire_and_release_vm(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.add_vm_to_pool(self.vm_ip, "alternative", self.group)
        self.test_vmm.do_vm_check(self.vm_name)
        self.test_vmm.do_vm_check("alternative")
        self.test_vmm.get_vm_by_name("alternative").store_field(self.test_vmm.rc, "bound_to_user", self.username)

        vmd_got_first = self.test_vmm.acquire_vm(group=self.group, username=self.username)
        assert vmd_got_first.vm_name == "alternative"

        self.test_vmm.release_vm("alternative")
        vmd_got_second = self.test_vmm.acquire_vm(group=self.group, username=self.username)
        assert vmd_got_second.vm_name == "alternative"

    def test_check_time(self, mc_time):
        self.checker.check_health.return_value = None

        mc_time.time.return_value = 1
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.do_vm_check(self.vm_name)
        self.test_vmm.add_vm_to_pool(self.vm_ip, "alternative", self.group)

        mc_time.time.return_value = int(0.7 * Thresholds.health_check_period)
        self.test_vmm.do_vm_check("alternative")

        mc_time.time.return_value = 1 + Thresholds.health_check_period
        self.checker.check_health.reset_mock()
        assert not self.checker.check_health.called
        mc_do_vm_check = MagicMock()
        self.test_vmm.do_vm_check = types.MethodType(mc_do_vm_check, self.test_vmm)
        assert not self.test_vmm.do_vm_check.called

        self.vm_daemon.check_ready_vms()

        assert self.test_vmm.do_vm_check.called
        assert not any(call_args[0][1] == "alternative" for call_args in mc_do_vm_check.call_args_list)

        mc_time.time.return_value = 1 + Thresholds.health_check_period * 2
        self.vm_daemon.check_ready_vms()
        assert any(call_args[0][1] == "alternative" for call_args in mc_do_vm_check.call_args_list)

    def test_remove_vm_from_pool_only_terminated(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        for state in [VmStates.IN_USE, VmStates.GOT_IP, VmStates.CHECK_HEALH, VmStates.READY, VmStates.TERMINATING]:
            self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "state", state)
            with pytest.raises(Exception):
                self.test_vmm.remove_vm_from_pool(self.vm_name)
        self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "state", VmStates.TERMINATED)
        self.test_vmm.remove_vm_from_pool(self.vm_name)

        with pytest.raises(Exception):
            self.test_vmm.get_vm_by_name(self.vm_name)

        assert self.test_vmm.rc.scard(KEY_VM_POOL.format(group=self.group)) == 0

    def test_terminate(self, capsys):
        my_remove = self.test_vmm.remove_vm_from_pool
        self.test_vmm.remove_vm_from_pool = types.MethodType(MagicMock(), self.test_vmm)
        self.test_vmm.terminator = self.terminator
        for state in [VmStates.IN_USE, VmStates.GOT_IP, VmStates.CHECK_HEALH, VmStates.READY, VmStates.TERMINATING]:
            self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
            self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "state", state)

            self.test_vmm.terminate_vm(self.vm_name)
            self.test_vmm.get_vm_by_name(self.vm_name).get_field(self.test_vmm.rc, "state") == VmStates.TERMINATING
            my_remove(self.vm_name)

        self.test_vmm.remove_vm_from_pool.reset_mock()
        assert not self.test_vmm.remove_vm_from_pool.called
        self.terminator.terminate.side_effect = Exception("foobar")
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "state", VmStates.READY)
        self.test_vmm.terminate_vm(self.vm_name)
        assert not self.test_vmm.remove_vm_from_pool.called

        capsys.readouterr()

    def test_terminate_publish(self):
        self.test_vmm.terminator = self.terminator
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)

        ps = self.test_vmm.rc.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(PUBSUB_VM_TERMINATION.format(vm_name=self.vm_name))
        while True:
            if ps.get_message() is None:
                break

        assert ps.get_message() is None
        self.test_vmm.terminate_vm(self.vm_name)
        time.sleep(0.2)
        msg = None
        while msg is None:
            msg = ps.get_message()
            time.sleep(0.1)

        assert ps.get_message() is None
        assert msg["data"] == VmStates.TERMINATING
        assert msg["type"] == "message"

    def test_register_spawned_vms(self):
        self.vm_daemon.subscribe_pubsub_channels()
        time.sleep(0.001)

        spawned_dict = {"vm_name": self.vm_name, "ip": self.vm_ip, "group": self.group}
        self.test_vmm.rc.publish(PUBSUB_SPAWNER, json.dumps(spawned_dict))

        time.sleep(0.2)
        self.vm_daemon.register_spawned_vms()
        self.vm_daemon.register_spawned_vms()

        vmd = self.test_vmm.get_vm_by_name(self.vm_name)
        assert vmd.vm_ip == self.vm_ip
        assert vmd.state == VmStates.GOT_IP
        # print("XXX>{}<".format(vmd))
