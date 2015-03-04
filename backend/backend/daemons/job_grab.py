# coding: utf-8

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import

from multiprocessing import Process
import time
from setproctitle import setproctitle
import sys

from requests import get, RequestException
from retask.task import Task
from retask.queue import Queue

from ..actions import Action
from ..constants import JOB_GRAB_REMOVE_PUBSUB
from ..helpers import get_redis_connection, format_tb
from ..exceptions import CoprJobGrabError
from ..frontend import FrontendClient


# TODO: Replace entire model with asynchronous queue, so that frontend push task,
# and workers listen for them
class CoprJobGrab(Process):

    """
    Fetch jobs from the Frontend

        - submit build task to the jobs queue for workers
        - run Action handler for action tasks


    :param Bunch opts: backend config
    :param events: :py:class:`multiprocessing.Queue` to listen
        for events from other backend components
    :param lock: :py:class:`multiprocessing.Lock` global backend lock

    """

    def __init__(self, opts, events, lock):
        # base class initialization
        super(CoprJobGrab, self).__init__(name="jobgrab")

        self.opts = opts
        self.events = events
        self.task_queues_by_arch = {}

        self.added_jobs = set()
        self.lock = lock

        self.rc = None
        self.rem_channel = None

    def connect_queues(self):
        """
        Connects to the retask queues. One queue per builders group.
        """
        for group in self.opts.build_groups:
            queue = Queue("copr-be-{0}".format(group["id"]))
            queue.connect()

            for arch in group["archs"]:
                self.task_queues_by_arch[arch] = queue

        self.rc = get_redis_connection(self.opts)
        self.rem_channel = self.rc.pubsub(ignore_subscribe_messages=True)
        self.rem_channel.subscribe(JOB_GRAB_REMOVE_PUBSUB)
        while self.rem_channel.get_message() is not None:
            pass

    def event(self, what):
        """
        Put new event into the event queue

        :param what: message to put into the queue
        """
        self.events.put({"when": time.time(), "who": "jobgrab", "what": what})

    def process_build_task(self, task):
        """
        Route build task to the appropriate queue.
        :param task: dict-like object which represent build task

        Utilized **task** keys:

            - ``task_id``
            - ``chroot``
            - ``arch``

        :return int: Count of the successfully routed tasks
        """
        count = 0
        if "task_id" in task:
            if task["task_id"] not in self.added_jobs:

                # TODO: produces memory leak!
                self.added_jobs.add(task["task_id"])
                arch = task["chroot"].split("-")[2]
                if arch not in self.task_queues_by_arch:
                    raise CoprJobGrabError("No builder group for architecture: {}, task: {}"
                                           .format(arch, task))

                task_obj = Task(task)
                self.task_queues_by_arch[arch].enqueue(task_obj)
                count += 1
            # else:
                # self.event("Task `{}` was already sent builder, ignoring".format(task["task_id"]))

        else:
            self.event("Task missing field `task_id`, raw task: {}".format(task))
        return count

    def process_action(self, action):
        """
        Run action task handler, see :py:class:`~backend.action.Action`

        :param action: dict-like object with action task
        """
        ao = Action(self.events, action, self.lock, destdir=self.opts.destdir,
                    frontend_callback=FrontendClient(self.opts, self.events),
                    front_url=self.opts.frontend_base_url,
                    results_root_url=self.opts.results_baseurl)
        ao.run()

    def load_tasks(self):
        """
        Retrieve tasks from frontend and runs appropriate handlers
        """
        try:
            r = get("{0}/waiting/".format(self.opts.frontend_url),
                    auth=("user", self.opts.frontend_auth))
        except RequestException as e:
            self.event("Error retrieving jobs from {0}: {1}"
                       .format(self.opts.frontend_url, e))
            return

        try:
            r_json = r.json()
        except ValueError as e:
            self.event("Error getting JSON build list from FE {0}".format(e))
            return

        if r_json.get("builds"):
            self.event("{0} jobs returned".format(len(r_json["builds"])))
            count = 0
            for task in r_json["builds"]:
                try:
                    count += self.process_build_task(task)
                except CoprJobGrabError as err:
                    self.event("Failed to enqueue new job: {} with error: {}"
                               .format(task, err))

            if count:
                self.event("New jobs: %s" % count)

        if r_json.get("actions"):
            self.event("{0} actions returned".format(len(r_json["actions"])))

            for action in r_json["actions"]:
                try:
                    self.process_action(action)
                except Exception as error:
                    self.event("Error during processing action `{}`: {}"
                               .format(action, error))

    def remove_jobs(self):
        """
        Listens for pubsub and remove jobs from self.added_jobs so we can re-add jobs failed due to VM error
        """
        self.event("Trying to rcv remove msg")
        while True:
            raw = self.rem_channel.get_message()
            self.event("Recv rem msg: ".format(raw))
            if raw is None:
                break
            if raw["type"] != "message":
                continue
            try:
                msg = raw["data"]
                if msg in self.added_jobs:
                    self.added_jobs.remove(msg)
                    self.event("Remove task from added_jobs".format(msg))
            except Exception as err:
                _, _, ex_tb = sys.exc_info()
                self.event("Error receiving message from remove pubsub: raw msg: {}, error: {}, traceback:\n{}"
                           .format(raw, err, format_tb(err, ex_tb)))

    def run(self):
        """
        Starts job grabber process
        """
        setproctitle("CoprJobGrab")
        self.connect_queues()
        try:
            while True:
                try:
                    self.remove_jobs()
                    self.load_tasks()

                    self.event("Added jobs after remove and load: {}".format(self.added_jobs))
                    time.sleep(self.opts.sleeptime)
                except Exception as err:
                    _, _, ex_tb = sys.exc_info()
                    self.event("Job Grab unhandled exception".format(err, format_tb(err, ex_tb)))

        except KeyboardInterrupt:
            return
