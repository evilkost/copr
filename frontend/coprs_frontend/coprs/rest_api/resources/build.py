# coding: utf-8

import flask
from flask import url_for
from coprs.logic.coprs_logic import CoprsLogic
from coprs.logic.builds_logic import BuildsLogic

from coprs.rest_api.util import get_one_safe

from flask_restful import Resource, reqparse


class BuildListR(Resource):

    def get(self):

        parser = reqparse.RequestParser()

        parser.add_argument('owner', type=str)
        parser.add_argument('project', type=str)

        parser.add_argument('limit', type=int)
        parser.add_argument('offset', type=int)

        req_args = parser.parse_args()

        kwargs = {}
        for key, trans in {"owner": "username", "project": "coprname"}.items():
            if req_args[key]:
                kwargs[trans] = req_args[key]

        query = BuildsLogic.get_multiple(None, **kwargs)

        if "limit" in req_args:
            query = query.limit(req_args["limit"])

        if "offset" in req_args:
            query = query.offset(req_args["offset"])

        builds = query.all()
        return {
            "links": {
                "self": url_for(BuildListR.endpoint, **req_args),
            },
            "builds": [
                {
                    "build": build.to_dict(),
                    "link": url_for(BuildR.endpoint, build_id=build.id),
                } for build in builds
            ]
        }


class BuildR(Resource):

    def get(self, build_id):

        build = get_one_safe(BuildsLogic.get(build_id),
                             "Not found build with id: {}".format(build_id))
        return {
            "build": build.to_dict(),
            "links": {
                "self": url_for(BuildR.endpoint, build_id=build_id),
                # TODO: can't do it due to circular imports
                # "parent_copr": url_for(CoprR.endpoint,
                #                        owner=build.copr.owner.name,
                #                        project=build.copr.name),
            }
        }




