# -*- coding: utf-8 -*-


from functools import partial
import logging
import signal
import time
import json

from concurrent.futures import ThreadPoolExecutor
import asyncio
from asyncio import coroutine, async, Future
import asyncio_redis

logging.getLogger("asyncio").setLevel(logging.WARN)
log = logging.getLogger(__name__)


class PeriodicTask(object):
    """
    :param name: task name
    :param fn: callable function
    :param period: minimal delay between two consecutive function invocation [seconds]
    :param cool_down: delay to start next invocation after previous one finished [seconds]
    """
    def __init__(self, name: str, fn: callable, period: int=None, cool_down: int=None):
        self.name = name
        self.fn = fn
        self.period = period or 0
        self.cool_down = cool_down or 0

    def get_delay(self, prev_started: int, prev_finished: int) -> int:
        cur_time = time.time()
        since_start = cur_time - prev_started
        since_finish = cur_time - prev_finished
        delay = max(0, self.period - since_start, self.cool_down - since_finish)
        return delay


def json_params_parser(msg: str) -> tuple:
    """
    :param msg: serialized string
    :return: ([args], {kwargs})
    """
    raw = json.loads(msg)
    return raw["args"], raw["kwargs"]


def json_params_serializer(*args, **kwargs) -> str:
    return json.dumps({"args": args, "kwargs": kwargs})


class OnDemandTask(object):
    """
    Represents tasks activated through message queue.
    Firstly we setup task (function to invoke and function to parse mq payload)

    :param name: task name
    :param channel: name of the redis pub-sub channel to listen
    :param fn: Target function to execute on receiving particular message
    :param parser: Parser queue message into the `fn` parameters [msg => (args, kwargs)]
    """
    def __init__(self, name: str, channel: str, fn: callable,
                 parser: callable=None, serializer: callable=None):
        self.name = name
        self.channel = channel
        self.fn = fn

        self.parser = parser or json_params_parser
        self.serializer = serializer or json_params_serializer


class Runner(object):
    def __init__(self, config):
        self.config = config
        self.loop = asyncio.get_event_loop()

        self.periodic_tasks = []  # List[PeriodicTask]
        self.on_demand_tasks = {}  # {channel -> OnDemandTask}

        self.pool = None
        # self.pool = ThreadPoolExecutor(6)
        # if we use dedicated processes we should setup centralized logging
        # self.pool = ProcessPoolExecutor(4)
        self.redis_connection = None

        self.is_running = False

    # def add_periodic_task(self, name, task_fn, period, cool_down=None):
    #     self.periodic_tasks.append(PeriodicTask(name, task_fn, period, cool_down))
    #
    # def add_on_demand_task(self, task: OnDemandTask):
    #     self.on_demand_tasks[task.channel] = task
    #
    # @coroutine
    # def run_task_periodic(self, pt: PeriodicTask):
    #     if self.is_running:
    #         log.debug("Executing periodic task: {}".format(pt.name))
    #         start_time = time.time()
    #         try:
    #             ft = self.loop.run_in_executor(self.pool, pt.fn)
    #             yield from ft  # now we cannot enforce timeout on task (
    #         except Exception:
    #             log.exception("Error during execution of {}".format(pt.name))
    #         else:
    #             log.debug("Task: {} finished in: {}".format(pt.name,  time.time() - start_time))
    #
    #         # next schedule next run
    #         if self.is_running:
    #             self.loop.call_later(pt.get_delay(start_time, time.time()),
    #                                  lambda: async(self.run_task_periodic(pt)))

    # @coroutine
    # def handle_on_demand(self, odt: OnDemandTask, data: str):
    #     try:
    #         args, kwargs = odt.parser(data)
    #     except Exception:
    #         log.exception("Failed to parse message from channel: {}, raw data: {}"
    #                       .format(odt.channel, data))
    #         return
    #
    #     ft = self.loop.run_in_executor(self.pool, partial(odt.fn, *args, **kwargs))
    #     start_time = time.time()
    #     log.debug("Executing on demand task: {}".format(odt.name))
    #     try:
    #         yield from ft  # now we cannot enforce timeout on task (
    #     except Exception:
    #         log.exception("Error during execution of {}".format(odt.name))
    #     log.debug("Task: {} finished in: {}".format(odt.name,  time.time() - start_time))
    #
    # @coroutine
    # def subscribe_on_demand_tasks(self):
    #     # todo: get host/port from self.config
    #     self.redis_connection = yield from asyncio_redis.Connection.create(
    #         host=self.config.get("redis_host"),
    #         port=self.config.get("redis_port"),
    #         db=self.config.get("redis_db")
    #     )
    #     # for channel, od_task in self.on_demand_tasks.items():
    #     subscriber = yield from self.redis_connection.start_subscribe()
    #     yield from subscriber.subscribe(list(self.on_demand_tasks.keys()))
    #     while self.is_running:
    #         reply = yield from subscriber.next_published()
    #         log.debug('Received: `{}` on channel `{}`'
    #                   .format(repr(reply.value), reply.channel))
    #         odt = self.on_demand_tasks[reply.channel]
    #         async(self.handle_on_demand(odt, reply.value))

    # Runner daemonization below
    @coroutine
    def stop(self):
        log.info("Stopping async runner ...")
        self.is_running = False

        if self.pool:
            self.pool.shutdown(wait=True)

        self.loop.stop()

        log.info("Finished ")

    def attach_signal_handlers(self):
        for sig_name in ('SIGINT', 'SIGTERM'):
            self.loop.add_signal_handler(
                getattr(signal, sig_name),
                lambda: async(self.stop()))

    def start(self):
        self.attach_signal_handlers()
        self.is_running = True
        # for pt in self.periodic_tasks:
        #     async(self.run_task_periodic(pt))
        # async(self.subscribe_on_demand_tasks())
        self.loop.run_forever()
