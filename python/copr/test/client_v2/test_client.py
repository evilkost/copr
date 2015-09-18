# coding: utf-8
import os
import copy
import tarfile
import tempfile
import shutil
import time

import six


if six.PY3:
    from unittest import mock
    from unittest.mock import MagicMock
else:
    import mock
    from mock import MagicMock

import pytest

@pytest.yield_fixture
def mc_requests():
    with mock.patch('backend.createrepo.Popen') as handle:
        yield handle



class TestClient(object):

    def setup_method(self, method):

        self.requests_patcher = mock.patch('')

