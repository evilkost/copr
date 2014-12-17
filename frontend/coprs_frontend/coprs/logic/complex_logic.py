# coding: utf-8

import flask
from .builds_logic import BuildsLogic
from .coprs_logic import CoprsLogic

class ComplexLogic(object):
    """
    Used for manipulation which affects multiply models
    """

    @classmethod
    def delete_copr(cls, copr):
        """
        Delete copr and all its builds.

        :param copr:
        :raises ActionInProgressException:
        :raises InsufficientRightsException:
        """
        builds_query = BuildsLogic.get_multiple(flask.g.user, copr=copr)
        for build in builds_query:
            BuildsLogic.delete_build(flask.g.user, build)
        CoprsLogic.delete_unsafe(flask.g.user, copr)
