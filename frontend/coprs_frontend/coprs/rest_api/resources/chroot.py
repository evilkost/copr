# coding: utf-8

import json
import flask
from flask import url_for
from flask_restful import Resource, reqparse

from marshmallow import Schema, fields, pprint

from coprs.views.misc import api_login_required
from coprs.logic.coprs_logic import MockChrootsLogic

from ..util import get_one_safe, json_loads_safe, mm_deserialize


class ChrootListR(Resource):

    def get(self):
        chroots = MockChrootsLogic.get_multiple(None).all()
        return {
            "links": {
                "self": url_for(ChrootListR.endpoint),
            },
            "chroots": [
                {
                    "chroot": chroot.to_dict(),
                    "link": url_for(ChrootR.endpoint, name=chroot.name),
                } for chroot in chroots
            ]
        }


class ChrootR(Resource):

    def get(self, name):
        chroot = get_one_safe(MockChrootsLogic.get_from_name(name))
        return {
            "links": {
                "self": url_for(ChrootR.endpoint, name=chroot.name)
            },
            "chroot": chroot.to_dict()
        }
