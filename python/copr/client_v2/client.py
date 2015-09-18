# coding: utf-8

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import

import json
import sys
import os
import logging
from marshmallow import pprint

import requests
import six

from six.moves import configparser
# from requests_toolbelt.multipart.encoder import MultipartEncoder

from .entities import parse_root, ProjectHandle, RootEntity
from client_v2.common import EntityTypes
from .net_client import NetClient

if sys.version_info < (2, 7):
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
else:
    from logging import NullHandler

from ..exceptions import CoprConfigException, CoprNoConfException, \
    CoprRequestException, \
    CoprUnknownResponseException



# from .responses import ProjectHandle, \
#     CoprResponse, BuildHandle, BaseHandle, ProjectChrootHandle
#
# from .parsers import fabric_simple_fields_parser, ProjectListParser, \
#     CommonMsgErrorOutParser, NewBuildListParser, ProjectChrootsParser, \
#    ProjectDetailsFieldsParser

from ..util import UnicodeMixin

log = logging.getLogger(__name__)
log.addHandler(NullHandler())


class CoprClient(UnicodeMixin):
    """ Main interface to the copr service

    :param NetClient net_client: wrapper for http requests
    :param unicode root_url: used as copr projects root
    :param bool no_config: helper flag to indicate that no config was provided

    Could be created:
        - using static method :py:meth:`CoprClient.create_from_file_config`
        - using static method :py:meth:`CoprClient.create_from_params`

    If you create Client directly call post_init() method after the creation.
    """

    def __init__(self, net_client, root_url=None, no_config=False):
        """

        """
        self.nc = net_client
        self.root_url = root_url or u"http://copr.fedoraproject.org"

        self.no_config = no_config

        self._main_resources = None

        self.root = None
        """:type : RootEntity or None """

        self.projects = None
        """:type : ProjectHandle or None """

    def __unicode__(self):
        return (
            u"<Copr client. api root url: {}, config provided: {}, net client: {}>"
            .format(self.root_url, not self.no_config, self.nc)
        )

    @property
    def api_root(self):
        """
            Url to API endpoint
        """
        return "{0}/api_2".format(self.root_url)

    @classmethod
    def create_from_params(cls, root_url=None, login=None, token=None):
        nc = NetClient(login, token)
        client = cls(nc, root_url, no_config=True)
        client.post_init()
        return client


    @classmethod
    def create_from_file_config(cls, filepath=None, ignore_error=False):
        """
        Creates Copr client using the information from the config file.

        :param filepath: specifies config location,
            default: "~/.config/copr"
        :type filepath: `str`
        :param bool ignore_error: When true and config is missing,
            creates default Client without credentionals

        :rtype: :py:class:`~.client.CoprClient`
        """
        raw_config = configparser.ConfigParser()
        if not filepath:
            filepath = os.path.join(os.path.expanduser("~"), ".config", "copr")
        config = {}
        if not raw_config.read(filepath):
            log.warning(
                "No configuration file '~/.config/copr' found. "
                "See man copr-cli for more information")
            config["no_config"] = True
            if not ignore_error:
                raise CoprNoConfException()
            else:
                client = cls.create_from_params()
        else:
            try:
                for field in ["login", "token", "copr_url"]:
                    if six.PY3:
                        config[field] = raw_config["copr-cli"].get(field, None)
                    else:
                        config[field] = raw_config.get("copr-cli", field, None)
                nc = NetClient(config["login"], config["token"])
                client = cls(nc, root_url=config["copr_url"], )

            except configparser.Error as err:
                if not ignore_error:
                    raise CoprConfigException(
                        "Bad configuration file: {0}".format(err))
                else:
                    client = cls.create_from_params()

        client.post_init()
        return client

    def post_init(self):
        log.debug("Getting root resources")
        response = self.nc.request(self.api_root)

        self.root = parse_root(response, self.root_url)
        self.projects = ProjectHandle(self.nc, self.root.get_resource_base_url(u"projects"))

        # import ipdb; ipdb.set_trace()
