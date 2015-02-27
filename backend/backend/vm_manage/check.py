# coding: utf-8

import weakref

import ansible
import ansible.runner
import ansible.utils
import time

from ..exceptions import MockRemoteError, CoprWorkerError, CoprWorkerSpawnFailError


class HealthChecker(object):

    def __init__(self, opts, events):
        self.opts = weakref.proxy(opts)
        self.events = events

    def log(self, msg):
        self.events.put({"when": time.time(), "who": "health_checker", "what": msg})

    def check_health(self, vm_ip):
        """
        Test connectivity to the VM

        :param vm_ip: ip address to the newly created VM
        :raises: :py:class:`~backend.exceptions.CoprWorkerSpawnFailError`: validation fails
        """
        runner_options = dict(
            remote_user="root",
            host_list="{},".format(vm_ip),
            pattern=vm_ip,
            forks=1,
            transport=self.opts.ssh.transport,
            timeout=500
        )
        connection = ansible.runner.Runner(**runner_options)
        connection.module_name = "shell"
        connection.module_args = "echo hello"

        try:
            res = connection.run()
        except Exception as exception:
            raise CoprWorkerSpawnFailError(
                "Failed to check  VM ({})"
                "due to ansible error: {}".format(vm_ip, exception))

        if vm_ip not in res.get("contacted", {}):
            self.callback.log(
                "VM is not responding to the testing playbook."
                "Runner options: {}".format(runner_options) +
                "Ansible raw response:\n{}".format(res))
            raise CoprWorkerSpawnFailError("Created VM ({}) was unresponsive "
                                           "and therefore terminated".format(vm_ip))
