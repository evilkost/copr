# coding: utf-8

import re

from IPy import IP

from ..exceptions import CoprWorkerSpawnFailError

#
# def try_spawn(self, args):
#     """
#     Tries to spawn new vm using ansible
#
#     :param args: ansible for ansible command which spawns VM
#     :return str: valid ip address of new machine (nobody guarantee machine availability)
#     """
#     result = self.run_ansible_playbook(args, "spawning instance")
#     if not result:
#         raise CoprWorkerSpawnFailError("No result, trying again")
#     match = re.search(r'IP=([^\{\}"]+)', result, re.MULTILINE)
#
#     if not match:
#         raise CoprWorkerSpawnFailError("No ip in the result, trying again")
#     ipaddr = match.group(1)
#     match = re.search(r'vm_name=([^\{\}"]+)', result, re.MULTILINE)
#
#     if match:
#         self.vm_name = match.group(1)
#     self.callback.log("got instance ip: {0}".format(ipaddr))
#
#     try:
#         IP(ipaddr)
#     except ValueError:
#         # if we get here we"re in trouble
#         msg = "Invalid IP back from spawn_instance - dumping cache output\n"
#         msg += str(result)
#         raise CoprWorkerSpawnFailError(msg)
#
#     return ipaddr
#
# def spawn_instance(self):
#     """
#     Spawn new VM, executing the following steps:
#
#         - call the spawn playbook to startup/provision a building instance
#         - get an IP and test if the builder responds
#         - repeat this until you get an IP of working builder
#
#     :param BuildJob job:
#     :return ip: of created VM
#     :return None: if couldn't find playbook to spin ip VM
#     """
#
#     start = time.time()
#
#     # Ansible playbook python API does not work here, dunno why.  See:
#     # https://groups.google.com/forum/#!topic/ansible-project/DNBD2oHv5k8
#
#     try:
#         spawn_playbook = self.opts.build_groups[self.group_id]["spawn_playbook"]
#     except KeyError:
#         return
#
#     spawn_args = "-c ssh {}".format(spawn_playbook)
#
#     # TODO: replace with for i in range(MAX_SPAWN_TRIES): ... else raise FatalError
#     i = 0
#     while self.vm_ip is None:
#         i += 1
#         try:
#             self.callback.log("Spawning a builder. Try No. {0}".format(i))
#
#             self.vm_ip = self.try_spawn(spawn_args)
#             self.update_process_title()
#             try:
#                 self.validate_vm()
#             except CoprWorkerSpawnFailError:
#                 self.terminate_instance()
#                 raise
#
#             self.callback.log("Instance spawn/provision took {0} sec"
#                               .format(time.time() - start))
#
#         except CoprWorkerSpawnFailError as exception:
#             self.callback.log("VM Spawn attempt failed with message: {}"
#                               .format(exception.msg))


class Spawner(object):

    def __init__(self, opts):
        """
        :param opts: Global backend configuration
        :type opts: Bunch
        """
        self.opts = opts

    def spawn(self):
        return "127.0.0.1"



