# -*- coding: utf-8 -*-



# import sys
# from asyncio import coroutine, get_event_loop
#
#
# import asyncssh
#
#
# class MySSHClientSession(asyncssh.SSHClientSession):
#     def data_received(self, data, datatype):
#         print("date received")
#         print(data, end='')
#         print("date received 2")
#
#     def connection_lost(self, exc):
#         if exc:
#             print('SSH session error: ' + str(exc), file=sys.stderr)
#
# class MySSHClient(asyncssh.SSHClient):
#     def connection_made(self, conn):
#         print('Connection made to %s.' % conn.get_extra_info('peername')[0])
#
#     def auth_completed(self):
#         print('Authentication successful.')
#
#
# @coroutine
# def exec_one_cmd(vm_ip: str, cmd: list, priv_key_path: str):
#     print("At {} executing cmd: {}".format(vm_ip, " ".join(cmd)))
#
#     conn, client = yield from asyncssh.create_connection(MySSHClient,
#                                                          vm_ip,
#                                                          client_keys=priv_key_path,
#                                                          known_hosts=None)
#     with conn:
#         chan, session = yield from conn.create_session(MySSHClientSession, "ls /")
#         yield from chan.wait_closed()
#
#     return 1
#
#
# if __name__ == "__main__":
#     loop = get_event_loop()
#     loop.run_until_complete(exec_one_cmd("46.101.165.191", ["ls", "/"], "/home/kost/.ssh/sub/do_kost"))
#     # loop.run_until_complete(exec_one_cmd("aether", ["echo", "hello"], "/home/kost/.ssh/sub/do_kost"))



# import asyncio, asyncssh, sys
#
# class MySSHClientSession(asyncssh.SSHClientSession):
#     def data_received(self, data, datatype):
#         print(data, end='')
#
#     def connection_lost(self, exc):
#         if exc:
#             print('SSH session error: ' + str(exc), file=sys.stderr)
#
# class MySSHClient(asyncssh.SSHClient):
#     def connection_made(self, conn):
#         print('Connection made to %s.' % conn.get_extra_info('peername')[0])
#
#     def auth_completed(self):
#         print('Authentication successful.')
#
# @asyncio.coroutine
# def run_client():
#     conn, client = yield from asyncssh.create_connection(MySSHClient, 'localhost', known_hosts=None)
#
#     with conn:
#         chan, session = yield from conn.create_session(MySSHClientSession, 'ls /')
#         yield from chan.wait_closed()
#
# try:
#     asyncio.get_event_loop().run_until_complete(run_client())
# except (OSError, asyncssh.Error) as exc:
#     sys.exit('SSH connection failed: ' + str(exc))