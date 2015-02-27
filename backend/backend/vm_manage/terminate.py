# coding: utf-8
import weakref
import time


class Terminator(object):

    def __init__(self, opts, events):
        self.opts = weakref.proxy(opts)
        self.events = events

    def log(self, msg):
        self.events.put({"when": time.time(), "who": "health_checker", "what": msg})
