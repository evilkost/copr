# coding: utf-8
import json
from multiprocessing import Process
from setproctitle import setproctitle
from threading import Thread
import time
import sys
from backend.helpers import format_tb
from backend.vm_manage import Thresholds, VmStates, PUBSUB_MB, EventTopics, KEY_VM_INSTANCE


def do_recycle(vmm):
    """
    Cleanup services
    :param vmm:
    :return:
    """
    while True:
        time.sleep(60)
        # vmm.checker.recycle()
        # vmm.spawner.recycle()
        vmm.terminator.recycle()

# KEYS[1]: VMD key
on_health_check_success_lua = """
local old_state = redis.call("HGET", KEYS[1], "state")
if old_state ~= "check_health" and old_state ~= "in_use" then
    return nil
else
    redis.call("HSET", KEYS[1], "check_fails", 0)
    if old_state == "check_health" then
        redis.call("HSET", KEYS[1], "state", "ready")
    end
end
"""


class EventHandler(Process):

    def __init__(self, vmm):
        super(EventHandler, self).__init__(name="EventHandler")
        self.vmm = vmm
        self.kill_received = False

        # self.do_recycle_proc = None
        self.handlers_map = {
            EventTopics.HEALTH_CHECK: self.on_health_check_result,
            EventTopics.VM_SPAWNED: self.on_vm_spawned,
            EventTopics.VM_TERMINATION_REQUEST: self.on_vm_termination_request,
            EventTopics.VM_TERMINATED: self.on_vm_termination_result,
        }
        self.lua_scripts = {}

    def post_init(self):
        self.lua_scripts["on_health_check_success"] = self.vmm.rc.register_script(on_health_check_success_lua)
        
    def on_health_check_result(self, msg):

        try:
            vmd = self.vmm.get_vm_by_name(msg["vm_name"])
            check_fails_count = int(vmd.get_field(self.vmm.rc, "check_fails") or 0)
        except Exception:
            self.vmm.log("VM record disappeared, ignoring health check results,  msg: {}"
                         .format(msg), who="on_health_check_result")
            return

        if msg["result"] == "OK":
            self.lua_scripts["on_health_check_success"](keys=[vmd.vm_key], args=[time.time()])
            self.vmm.log("recording success for ip:{} name:{} "
                         .format(vmd.vm_ip, vmd.vm_name), who="on_health_check_result")
        else:
            if vmd.state == VmStates.GOT_IP:
                self.vmm.log("New VM doesn't respond to ping: {}, terminating"
                             .format(msg), who="on_health_check_result")
                self.vmm.terminate_vm(vmd.vm_name)
            else:
                self.vmm.log("recording check fail: {}".format(msg), who="on_health_check_result")
                vmd.record_failure(self.vmm.rc)
                if check_fails_count + 1 > Thresholds.max_check_fails:
                    self.vmm.log("check fail threshold reached: {}, terminating: {}"
                                 .format(check_fails_count, msg), who="on_health_check_result")
                    self.vmm.terminate_vm(vmd.vm_name)
    
    def on_vm_spawned(self, msg):
        self.vmm.add_vm_to_pool(msg["vm_ip"], msg["vm_name"], msg["group"])

    def on_vm_termination_request(self, msg):
        self.vmm.terminator.terminate_vm(group=msg["group"], vm_name=msg["vm_name"], vm_ip=msg["vm_ip"])

    def on_vm_termination_result(self, msg):
        if msg["result"] == "OK":
            self.vmm.log("Vm terminated, removing from pool ip: {}, name: {}, msg: {}"
                         .format(msg.get("vm_ip"), msg.get("vm_name"), msg.get("msg")))
            self.vmm.remove_vm_from_pool(msg["vm_name"])
        else:
            self.vmm.log("Vm termination failed ip: {}, name: {}, msg: {}"
                         .format(msg.get("vm_ip"), msg.get("vm_name"), msg.get("msg")))

    def run(self):
        setproctitle("Event Handler")

        self.post_init()

        self.do_recycle_proc = Thread(target=do_recycle, args=(self.vmm,))
        self.do_recycle_proc.start()

        self.init_pubsub_handler()

    def terminate(self):
        self.kill_received = True
        self.do_recycle_proc.terminate()
        self.do_recycle_proc.join()

    def init_pubsub_handler(self):
        """
        Listens redis pubsub and perform requested actions.
        Message payload is packed in json, it should be a dictionary
            at the root level with reserved field `topic` which is required
            for message routing
        :type vmm: VmManager
        """
        setproctitle("Event handler")
        channel = self.vmm.rc.pubsub(ignore_subscribe_messages=True)
        channel.subscribe(PUBSUB_MB)
        # TODO: check subscribe success
        self.vmm.log("Spawned pubsub handler", who="pubsub handler")
        for raw in channel.listen():
            if self.kill_received:
                break
            if raw is None:
                continue
            else:
                if raw["type"] != "message":
                    continue
                try:
                    msg = json.loads(raw["data"])

                    if "topic" not in msg:
                        raise Exception("Handler received msg without `topic` field, msg: {}".format(msg))
                    topic = msg["topic"]
                    if topic not in self.handlers_map:
                        raise Exception("Handler received msg with unknown `topic` field, msg: {}".format(msg))

                    self.handlers_map[topic](msg)

                except Exception as err:
                    _, _, ex_tb = sys.exc_info()
                    self.vmm.log("Handler error: raw msg: {},  {} {}"
                                 .format(raw, err, format_tb(err, ex_tb)), who="event handler")
