# -*- coding: utf-8 -*-

"""
Replacement for dispatcher.py
Periodically lookup into redis for pending task-s. If constraints[*] are satisfied push new
worker into the MpPool

[*] mainly number of running builds per project owner and VM availability
"""
import logging

from concurrent.futures import ProcessPoolExecutor
import asyncio
from asyncio import coroutine, async
from functools import partial

from backend.daemons.aio_runner import Runner
from backend.frontend import FrontendClient


log = logging.getLogger(__name__)


# def build_one(config, task_id, vm_name):
#     w = Worker(config, FrontendClient(config), )

class BuildRunner(Runner):

    def __init__(self, *args, **kwargs):
        super(BuildRunner, self).__init__(*args, **kwargs)
        self.pool = ProcessPoolExecutor(self.config["workers"])
        self.fc = FrontendClient(self.config)

    @coroutine
    def announce_start(self, build_task):
        # todo: add implementation
        yield from asyncio.sleep(1)

    @coroutine
    def announce_end(self, build_task):
        # todo: add implementation
        yield from asyncio.sleep(1)

    @coroutine
    def do_job(self, build_task):
        yield from self.announce_start(build_task)
        try:
            ft = self.loop.run_in_executor(self.pool, partial(odt.fn, build_task))
            yield from ft
        except Exception as err:
            log.exception("error during the build")

        yield from self.announce_end(build_task)

    @coroutine
    def schedule(self):
        yield from asyncio.sleep(1)
        # add new async if can
        if self.is_running:
            self.loop.call_later(30, lambda: async(self.schedule()))

    def start(self):
        async(self.schedule())
        super(BuildRunner, self).start()
