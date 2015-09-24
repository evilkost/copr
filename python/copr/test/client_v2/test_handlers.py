# coding: utf-8
import os
import copy
import tarfile
import tempfile
import shutil
import time

import six
import sys
import json
from copr.client_v2.net_client import ResponseWrapper

if six.PY3:
    from unittest import mock
    from unittest.mock import MagicMock
else:
    import mock
    from mock import MagicMock

import pytest

from copr.client_v2.handlers import ProjectHandle, ProjectChrootHandle


class TestHandleBase(object):

    def setup_method(self, method):

        self.nc = MagicMock()
        self.client = MagicMock()

        self.root_url = "http://example.com/api"
        self.response = MagicMock()

        self.root_json = {
            "_links": {
                "mock_chroots": {
                    "href": "/api_2/mock_chroots"
                },
                "self": {
                    "href": "/api_2/"
                },
                "projects": {
                    "href": "/api_2/projects"
                },
                "builds": {
                    "href": "/api_2/builds"
                },
                "build_tasks": {
                    "href": "/api_2/build_tasks"
                }
            }
        }

    def get_href(self, name):
        return self.root_json["_links"][name]["href"]


    @pytest.fixture
    def project_handle(self):
        return ProjectHandle(self.client, self.nc, self.root_url,
                             self.get_href("projects"))

    def make_response(self, json_string, status=200, headers=None):
        response = MagicMock()
        response.status_code = status
        response.headers = headers or dict()
        response.content = json_string
        return ResponseWrapper(response)


class TestProjectHandle(TestHandleBase):

    project_1 = """{
        "project": {
            "description": "A simple KDE respin",
            "disable_createrepo": false,
            "repos": [],
            "contact": null,
            "owner": "jmiahman",
            "build_enable_net": true,
            "instructions": "",
            "homepage": null,
            "id": 2482,
            "name": "Synergy-Linux"
        },
        "project_chroots": [
            {
                "chroot": {
                    "comps": null,
                    "comps_len": 0,
                    "buildroot_pkgs": [],
                    "name": "fedora-19-x86_64",
                    "comps_name": null
                },
                "_links": null
            }
        ],
        "project_builds": [
            {
                "_links": null,
                "build": {
                    "enable_net": true,
                    "source_metadata": {
                        "url": "http://miroslav.suchy.cz/copr/copr-ping-1-1.fc20.src.rpm"
                    },
                    "submitted_on": 1422379448,
                    "repos": [],
                    "results": "https://copr-be.cloud.fedoraproject.org/results/jmiahman/Synergy-Linux/",
                    "started_on": 1422379466,
                    "source_type": 1,
                    "state": "succeeded",
                    "source_json": "{\\"url\\": \\"http://dl.kororaproject.org/pub/korora/releases/21/source/korora-welcome-21.6-1.fc21.src.rpm\\"}",
                    "ended_on": 1422379584,
                    "timeout": 21600,
                    "pkg_version": "21.6-1.fc21",
                    "id": 69493,
                    "submitter": "asamalik"
                }
            }
        ],
        "_links": {
            "self": {
              "href": "/api_2/projects/2482?show_builds=True&show_chroots=True"
            },
            "chroots": {
              "href": "/api_2/projects/2482/chroots"
            },
            "builds": {
              "href": "/api_2/builds?project_id=2482"
            }
        }
    }"""
    project_1_id = 2482
    project_1_owner = "jmiahman"
    project_1_name = "Synergy-Linux"

    def test_get_one(self, project_handle):
        response = self.make_response(self.project_1)
        self.nc.request.return_value = response
        project = project_handle.get_one(
            self.project_1_id,
        #    show_builds=True, show_chroots=True
        )

        assert project.name == self.project_1_name
        assert project.owner == self.project_1_owner

