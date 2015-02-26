# coding: utf-8

class Spawner(object):

    def __init__(self, opts):
        """
        :param opts: Global backend configuration
        :type opts: Bunch
        """
        self.opts = opts

    def spawn(self):
        return "127.0.0.1"
