# -*- coding: utf-8 -*-

import os
import json
import tempfile
import shutil
import time
import tarfile
from bunch import Bunch

import pytest
import six


if six.PY3:
    from unittest import mock
    from unittest.mock import MagicMock
else:
    import mock
    from mock import MagicMock


from backend.helpers import get_redis_connection
from backend.build_task import BuildTask, add_build_task


class TestBuildTask(object):

    def setup_method(self, method):
        self.test_root_path = tempfile.mkdtemp()
        self.terminate_pb_path = "{}/terminate.yml".format(self.test_root_path)
        self.opts = Bunch(
            redis_db=9,
            redis_port=7777,
        )

        self.rc = get_redis_connection(self.opts)
        self.rc.flushdb()

        self.task_id_1 = "12345"
        self.task_dict_1 = dict(
            task_id="12345",
            chroot="fedora-20-x86_64",
            project_owner="foobar",
        )
        self.task_dict_2 = dict(
            task_id="12346",
            chroot="fedora-20-armv7",
            project_owner="foobar",
        )
        self.task_dict_bad_arch = dict(
            task_id="12346",
            chroot="fedora-20-s390x",
            project_owner="foobar",
        )

    def test_create_save_load(self):
        with pytest.raises(Exception):
            BuildTask.get(self.rc, self.task_id_1)

        bt = add_build_task(self.rc, 0, self.task_dict_1)

        assert bt.status == "pending"
        with pytest.raises(Exception):
            bt.non_existing_field = 1
        bt.arch = "i386"
        bt2 = BuildTask.get(self.rc, self.task_id_1)
        assert bt2.arch == "i386"

        print(bt2)
