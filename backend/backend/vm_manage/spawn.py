# coding: utf-8
import json
import os

import re

from pprint import pprint
import weakref
from IPy import IP
import time
from multiprocessing import Process, Queue
from redis import StrictRedis

from ..ans_utils import run_ansible_playbook, run_ansible_playbook_once
from backend.helpers import get_redis_connection
from backend.vm_manage import PUBSUB_SPAWNER
from ..exceptions import CoprWorkerSpawnFailError


def try_spawn(args, log_fn=None):
    """
    Tries to spawn new vm using ansible

    :param args: ansible for ansible command which spawns VM
    :return str: valid ip address of new machine (nobody guarantee machine availability)
    """
    if log_fn is None:
        log_fn = lambda x: pprint(x)

    result = run_ansible_playbook(args, name="spawning instance",
                                  retry_sleep_time=10.0, attempts=1)
    if not result:
        raise CoprWorkerSpawnFailError("No result, trying again")
    match = re.search(r'IP=([^\{\}"]+)', result, re.MULTILINE)

    if not match:
        raise CoprWorkerSpawnFailError("No ip in the result, trying again")
    ipaddr = match.group(1)
    match = re.search(r'vm_name=([^\{\}"]+)', result, re.MULTILINE)

    if match:
        vm_name = match.group(1)
    else:
        raise CoprWorkerSpawnFailError("No vm_name in the playbook output")
    log_fn("got instance ip: {0}".format(ipaddr))

    try:
        IP(ipaddr)
    except ValueError:
        # if we get here we"re in trouble
        msg = "Invalid IP back from spawn_instance - dumping cache output\n"
        msg += str(result)
        raise CoprWorkerSpawnFailError(msg)

    return {"ip": ipaddr, "vm_name": vm_name}


def spawn_instance(spawn_playbook, log_fn=None):
    """
    Spawn new VM, executing the following steps:

        - call the spawn playbook to startup/provision a building instance
        - get an IP and test if the builder responds
        - repeat this until you get an IP of working builder

    :param BuildJob job:
    :return ip: of created VM
    :return None: if couldn't find playbook to spin ip VM
    """
    if log_fn is None:
        log_fn = lambda x: pprint(x)
    log_fn("Spawning a builder")

    start = time.time()
    # Ansible playbook python API does not work here, dunno why.  See:
    # https://groups.google.com/forum/#!topic/ansible-project/DNBD2oHv5k8

    spawn_args = "-c ssh {}".format(spawn_playbook)
    try:
        result = run_ansible_playbook_once(spawn_args, name="spawning instance", log_fn=log_fn)
    except Exception as err:
        raise CoprWorkerSpawnFailError("Error during ansible invocation: {}".format(err.__dict__))

    if not result:
        raise CoprWorkerSpawnFailError("No result, trying again")
    match = re.search(r'IP=([^\{\}"]+)', result, re.MULTILINE)

    if not match:
        raise CoprWorkerSpawnFailError("No ip in the result, trying again")
    ipaddr = match.group(1)
    match = re.search(r'vm_name=([^\{\}"]+)', result, re.MULTILINE)

    if match:
        vm_name = match.group(1)
    else:
        raise CoprWorkerSpawnFailError("No vm_name in the playbook output")
    log_fn("got instance ip: {0}".format(ipaddr))

    try:
        IP(ipaddr)
    except ValueError:
        # if we get here we"re in trouble
        msg = "Invalid IP back from spawn_instance - dumping cache output\n"
        msg += str(result)
        raise CoprWorkerSpawnFailError(msg)

    log_fn("Instance spawn/provision took {0} sec".format(time.time() - start))
    return {"ip": ipaddr, "vm_name": vm_name}


def do_spawn_and_publish(opts, events, spawn_playbook, group):

    def log_fn(msg):
        events.put({"when": time.time(), "who": "spawner", "what": msg})

    try:
        log_fn("Going to spawn")
        spawn_result = spawn_instance(spawn_playbook, log_fn)
        log_fn("Spawn finished")
    except CoprWorkerSpawnFailError as err:
        log_fn("Failed to spawn builder: {}".format(err))
        return
    except Exception as err:
        log_fn("[Unexpected] Failed to spawn builder: {}".format(err))
        return

    spawn_result["group"] = group
    try:
        rc = get_redis_connection(opts)
        rc.publish(PUBSUB_SPAWNER, json.dumps(spawn_result))
    except Exception as err:
        log_fn("Failed to publish msg about new VM: {} with error: {}"
               .format(spawn_result, err))


class Spawner(object):

    def __init__(self, opts, events):
        """
        :param opts: Global backend configuration
        :type opts: Bunch
        """
        self.opts = weakref.proxy(opts)
        self.events = events

        self.child_processes = []

    def log(self, msg):
        self.events.put({"when": time.time(), "who": "spawner", "what": msg})

    def start_spawn(self, group):
        self.recycle()
        try:
            spawn_playbook = self.opts.build_groups[group]["spawn_playbook"]
            os.path.exists(spawn_playbook)
        except KeyError:
            msg = "Config missing playbook for group: {}".format(group)
            self.log(msg)
            raise CoprWorkerSpawnFailError(msg)
        except OSError:
            msg = "Playbook {} is missing".format(spawn_playbook)
            self.log(msg)
            raise CoprWorkerSpawnFailError(msg)

        proc = Process(target=do_spawn_and_publish,
                       args=(self.opts, self.events, spawn_playbook, group))
        self.child_processes.append(proc)
        proc.start()
        self.log("Spawn process started: {}".format(proc.pid))

    def terminate(self):
        for proc in self.child_processes:
            proc.terminate()

    def recycle(self):
        """
        Cleanup unused process, should be invoked periodically
        """
        still_alive = []
        for proc in self.child_processes:
            if proc.is_alive():
                still_alive.append(proc)
            else:
                self.log("Spawn process finished: {}".format(proc.pid))
        self.child_processes = still_alive

    def still_working(self):
        self.recycle()
        return len(self.child_processes) > 0

