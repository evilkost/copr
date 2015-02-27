# coding: utf-8
import json
import subprocess
from subprocess import CalledProcessError
import sys
import time

ansible_playbook_bin = "ansible-playbook"


def ans_extra_vars_encode(extra_vars, name):
    """ transform dict into --extra-vars="json string" """
    if not extra_vars:
        return ""
    return "--extra-vars='{{\"{0}\": {1}}}'".format(name, json.dumps(extra_vars))


def run_ansible_playbook(args, retry_sleep_time=30, name="running playbook", callback=None, attempts=9):
    """
    Call ansible playbook:

        - well mostly we run out of space in OpenStack so we rather try
          multiple times (attempts param)
        - dump any attempt failure
    """

    # Ansible playbook python API does not work here, dunno why.  See:
    # https://groups.google.com/forum/#!topic/ansible-project/DNBD2oHv5k8
    if callback is None:
        log = lambda x: None
    else:
        log = lambda x: callback.log(x)

    command = "{} {}".format(ansible_playbook_bin, args)
    result = None
    for i in range(0, attempts):
        try:
            attempt_desc = ": retry: " if i > 0 else ": begin: "
            log(name + attempt_desc + command)
            result = subprocess.check_output(command, shell=True)
            log("Raw playbook output:\n{0}\n".format(result))
            break

        except CalledProcessError as e:
            log("CalledProcessError: \n{0}\n".format(e.output))
            sys.stderr.write("{0}\n".format(e.output))
            # FIXME: this is not purpose of opts.sleeptime
            # time.sleep(self.opts.sleeptime)
            time.sleep(retry_sleep_time)

    log(name + ": end")
    return result
