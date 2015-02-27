# coding: utf-8

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from collections import defaultdict

from multiprocessing import Process
import time
from setproctitle import setproctitle
import weakref

from requests import get, RequestException
from retask.task import Task
from retask.queue import Queue

from ..actions import Action
from ..exceptions import CoprJobGrabError
from ..frontend import FrontendClient

from ..vm_manage.spawn import Spawner
from ..vm_manage.terminate import Terminator
from ..vm_manage.check import HealthChecker


class EventCallback(object):
    """
    :param events: :py:class:`multiprocessing.Queue` to listen
        for events from other backend components
    """
    def __init__(self, events):
        self.events = events

    def log(self, msg):
        self.events.put({"when": time.time(), "who": "vm_master", "what": msg})


class VmMaster(Process):
    """
    Spawns and terminate VM for builder process. Mainly wrapper for ..vm_manage package.

    :param Bunch opts: backend config
    :param events: :py:class:`multiprocessing.Queue` to listen
        for events from other backend components
    """

    def __init__(self, opts, events):
        Process.__init__(self, name="VM master")

        self.opts = weakref.proxy(opts)
        self.events = events
        #
        self.callback = None
        self.checker = None
        self.spawner = None
        self.terminater = None

    def post_init(self):
        self.callback = EventCallback(self.events)
        self.checker = HealthChecker(self.opts, self.callback)

    def run(self):
        """
        Start VM master process
        :return:
        """
        self.post_init()
