# coding: utf-8
from Queue import Empty
import copy

from collections import defaultdict
import json
from pprint import pprint
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
from backend.helpers import get_redis_connection
from backend.vm_manage import VmStates, Thresholds, KEY_VM_POOL, PUBSUB_VM_TERMINATION, PUBSUB_SPAWNER
from backend.vm_manage.check import HealthChecker
from backend.vm_manage.manager import VmManager
from backend.vm_manage.models import VmDescriptor
from backend.vm_manage.spawn import Spawner, do_spawn_and_publish

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
    with mock.patch("backend.vm_manage.spawn.time") as handle:
        yield handle


@pytest.yield_fixture
def mc_spawn_instance():
    with mock.patch("backend.vm_manage.spawn.spawn_instance") as handle:
        yield handle


class TestSpawner(object):

    def setup_method(self, method):
        self.opts = Bunch(
            redis_db=9,
            ssh=Bunch(
                transport="ssh"
            ),
            build_groups={
                0: {
                    "spawn_playbook": "/spawn.yml"
                }
            }
        )
        # self.callback = TestCallback()
        self.checker = MagicMock()
        self.terminator = MagicMock()

        self.queue = Queue()

        self.spawner = Spawner(self.opts, self.queue)

        self.vm_ip = "127.0.0.1"
        self.vm_name = "localhost"
        self.group = "x86"
        self.username = "bob"

        self.rc = get_redis_connection(self.opts)

    def teardown_method(self, method):
        keys = self.rc.keys("*")
        if keys:
            self.rc.delete(*keys)

    def _get_all_from_queue(self):
        res = []
        while True:
            try:
                time.sleep(0.01)
                value = self.queue.get_nowait()
                res.append(value)
            except Empty:
                break
        return res

    def test_pass(self):
        self.rc.set("foo", "bar")

    def test_log(self):
        self.spawner.log("foobar")
        logged = self._get_all_from_queue()
        assert len(logged) == 1
        assert logged[0]["what"] == "foobar"

    def test_do_spawn_and_publish(self, mc_spawn_instance):
        mc_spawn_instance.return_value = {"vm_name": self.vm_name, "ip": self.vm_ip}

        # ps = self.rc.pubsub(ignore_subscribe_messages=True)
        ps = self.rc.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(PUBSUB_SPAWNER)
        time.sleep(0.1)
        ps.get_message()  # ignoring

        do_spawn_and_publish(self.opts, self.queue, "/spawn.yml", group=0)
        msg = ps.get_message()
        assert json.loads(msg["data"]) == mc_spawn_instance.return_value

        logged = self._get_all_from_queue()
        print("\n Logged: {}".format(logged))

    def test_start_spawn(self, mc_spawn_instance):
        mc_spawn_instance.return_value = {"vm_name": self.vm_name, "ip": self.vm_ip}

        self.spawner.start_spawn(0)
        start = time.time()
        while self.spawner.still_working():
            time.sleep(0.002)
            print("time: {}".format(time.time() - start))

        print("Still alive: {}".format(self.spawner.still_working()))

        for ev in self._get_all_from_queue():
            pprint(ev)
