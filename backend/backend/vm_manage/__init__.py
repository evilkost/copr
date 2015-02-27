# coding: utf-8


class VmStates(object):
    GOT_IP = "got_ip"
    CHECK_HEALH = "check_health"
    READY = "ready"
    IN_USE = "in_use"
    TERMINATING = "terminating"
    TERMINATED = "terminated"  # can be safely removed from pool


PUBSUB_VM_TERMINATION = "copr:backend:vm_termination:pubsub::"
KEY_VM_GROUPS = "copr:backend:vm_groups:set::"
KEY_VM_POOL = "copr:backend:vm_pool:set::{group}"
KEY_VM_INSTANCE = "copr:backend:vm_instance:hset::{vm_name}"


class Thresholds(object):
    """
    Time constants for VM manager, all values are int and represents seconds
    """
    terminating_timeout = 600
    health_check_period = 300
    keep_vm_for_user_timeout = 600
    vm_spawn_min_interval = 30
    max_in_user_time = 3600 * 7
    cycle_timeout = 10
