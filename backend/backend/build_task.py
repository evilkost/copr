# -*- coding: utf-8 -*-
from asyncio import coroutine
import time

from redis import StrictRedis
from datetime import date
from marshmallow import Schema, fields, pprint


class BuildTaskSchema(Schema):
    status = fields.Str()
    chroot = fields.Str()


"""
This module should be use with sync version of redis api
"""
# TODO: use marshmallow for field access, i.e. str -> int marshalling
class BuildTask(object):
    """
    WARNING!
    For atomic changes of multiply fields write dedicated method with pipeline or
    LUA script with check for pre-conditions
    """

    PREFIX = "copr_bt:hset::"
    FIELDS = [
        "status",

        "chroot",
        "build_id",

        "arch",

        "task_added_on",
        "used_by_pid",

        "build_attempts",

        "timeout",
        "memory_reqs",
        "enable_net",

        "project_owner",
        "project_name",
        "submitter",

        "ended_on",
        "started_on",
        "submitted_on",

        "buildroot_pkgs",

        "pkg",
        "pkg_main_version",
        "pkg_epoch",
        "pkg_release",

        "built_packages",
    ]

    def __init__(self, redis_connection, task_id):
        """
        :param StrictRedis redis_connection:
        :param task_id:
        :return:
        """
        self.__dict__["redis_connection"] = redis_connection
        self.__dict__["task_id"] = task_id

    def exists(self, task_id):
        return self.redis_connection.exists(self.PREFIX + task_id)

    @classmethod
    def get(cls, redis_connection, task_id):
        bt = cls(redis_connection, task_id)
        if not bt.exists(task_id):
            raise ValueError("No such task are stored: {}".format(task_id))
        return bt

    def __getattr__(self, key):
        if key not in self.FIELDS:
            raise KeyError(key)
        return self.redis_connection.hget(self.PREFIX + self.task_id, key).decode("utf-8")

    def __setattr__(self, key, value):
        if key not in self.FIELDS:
            raise KeyError(key)
        self._store_kv(key, value)

    def _store_kv(self, key, value, connection=None):
        """
        wrapper for hset
        :param connection: RedisConnection or Pipeline object
        """
        if connection is None:
            connection = self.redis_connection
        connection.hset(self.PREFIX + self.task_id, key, value)

    def __str__(self):
        return "<BuildTask: {}>".format(" ".join(
            "{}:`{}`".format(k.decode("utf-8"), v.decode("utf-8")) for k, v in
            self.redis_connection.hgetall(self.PREFIX + self.task_id).items()))

BTI_SET_KEY = "copr_bt_index:set"
BTI_SET_BY_VM_GROUP = "copr_bt_by_group:{}:set"

class BuildTaskIndexes(object):
    def __init__(self, redis_connection: StrictRedis):
        self.redis_connection = redis_connection

    def __contains__(self, task_id):
        return self.redis_connection.sismember(BTI_SET_KEY, task_id)

    def insert(self, task_id, group):
        self.redis_connection.sadd(BTI_SET_BY_VM_GROUP.format(group), task_id)
        self.redis_connection.sadd(BTI_SET_KEY, task_id)

    def remove(self, task_id):
        return self.redis_connection.srem(BTI_SET_KEY, task_id)

    def get_all_by_group(self, group):
        return [task_id.decode("utf-8") for task_id in
                self.redis_connection.smembers(BTI_SET_BY_VM_GROUP.format(group))]

class AsyncBuildTaskIndexes(object):

    @staticmethod
    @coroutine
    def get_pending_task_obj(async_rc):
        pass


def add_build_task(rc: StrictRedis, group: int, task_dict: dict):
    with rc.pipeline() as pipe:
        task_id = str(task_dict.pop("task_id"))
        bt = BuildTask(pipe, task_id)

        # todo: replace with lua to avoid race

        bt.status = "pending"
        bt.task_added_on = time.time()
        bt.build_attempts = 0
        for k, v in task_dict.items():
            setattr(bt, k, v)

        bti = BuildTaskIndexes(pipe)
        bti.insert(task_id, group)

        pipe.execute()

    return BuildTask(rc, task_id)