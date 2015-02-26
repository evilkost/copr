# coding: utf-8


class VmStates(object):
    GOT_IP = "got_ip"
    CHECK_HEALH = "check_health"
    READY = "ready"
    IN_USE = "in_use"
    TERMINATING = "terminating"


KEY_VM_POOL = "copr:backend:vm_pool:set::{group}"
KEY_VM_INSTANCE = "copr:backend:vm_instance:hset::{vm_name}"
