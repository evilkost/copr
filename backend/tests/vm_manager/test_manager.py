# coding: utf-8
import copy

from collections import defaultdict
from bunch import Bunch
from backend.exceptions import MockRemoteError, CoprSignError, BuilderError

import tempfile
import shutil
import os

import six
from backend.vm_manage import VmStates
from backend.vm_manage.checker import HealthChecker
from backend.vm_manage.manager import VmManager
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
"""

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

        self.test_vmm = VmManager(self.opts, callback=self.callback, checker=self.checker)
        self.test_vmm.post_init()

        self.vm_ip = "127.0.0.1"
        self.vm_name = "localhost"
        self.group = "x86"
        self.username = "bob"

    def teardown_method(self, method):
        keys = self.test_vmm.rc.keys("*")
        self.test_vmm.rc.delete(*keys)

    def _test_add_vm_to_pool(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)

        vm_list = self.test_vmm.get_all_vm_in_group()

        vm = self.test_vmm.get_vm_by_name(self.vm_name)
        assert len(vm_list) == 1
        assert vm_list[0].__dict__ == vm.__dict__
        print(vm)

    def _test_check_vm(self):
        self.checker.check_health.return_value = None

        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.do_vm_check(self.vm_name)
        print()
        print(self.test_vmm.get_vm_by_name(self.vm_name))

        # self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "state", VmStates.IN_USE)

        # assert not self.test_vmm.do_vm_check(self.vm_name)
        self.test_vmm.do_vm_check(self.vm_name)
        print()
        print(self.test_vmm.get_vm_by_name(self.vm_name))

        self.test_vmm.get_vm_by_name(self.vm_name).store_field(self.test_vmm.rc, "bound_to_user", "bob")
        self.test_vmm.do_vm_check(self.vm_name)
        print()
        print(self.test_vmm.get_vm_by_name(self.vm_name))

    def test_acquire_vm(self):
        self.test_vmm.add_vm_to_pool(self.vm_ip, self.vm_name, self.group)
        self.test_vmm.do_vm_check(self.vm_name)
        self.test_vmm.acquire_vm(group=self.group, username=self.username)
        with pytest.raises(Exception):
            self.test_vmm.acquire_vm(group=self.group, username=self.username)
