# coding: utf-8

import flask
from flask import url_for
from flask_restful_swagger import swagger
from coprs.logic.coprs_logic import CoprsLogic
from coprs.logic.builds_logic import BuildsLogic

from coprs.rest_api.util import get_one_safe, bp_url_for

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
                "self": bp_url_for(BuildListR.endpoint, **req_args),
            },
            "builds": [
                {
                    "build": build.to_dict(),
                    "link": bp_url_for(BuildR.endpoint, build_id=build.id),
                } for build in builds
            ]
        }


@swagger.model
class BuildItem(object):
    def __init__(self, build_id):
        pass

class BuildR(Resource):
    @swagger.operation(
        # summary='Get single build by id',
        # responseClass=BuildItem.__name__,
        # responseMessages=[
        #     {
        #         "code": 404,
        #         "message": "No such build"
        #     }
        # ]
        # nickname='get',
        # Parameters can be automatically extracted from URLs (e.g. <string:id>)
        # but you could also override them here, or add other parameters.
        # parameters=[
        #     {
        #         "name": "build_id",
        #         "description": "Build id for lookup",
        #         "required": True,
        #         "allowMultiple": False,
        #         "dataType": 'int',
        #         "paramType": "path"
        #     },
        # ]
    )
    def get(self, build_id):
        """
        Get single build by id
        """
        build = get_one_safe(BuildsLogic.get(build_id),
                             "Not found build with id: {}".format(build_id))
        return {
            "build": build.to_dict(),
            "links": {
                "self": bp_url_for(BuildR.endpoint, build_id=build_id),
                # TODO: can't do it due to circular imports
                # "parent_copr": url_for(CoprR.endpoint,
                #                        owner=build.copr.owner.name,
                #                        project=build.copr.name),
            }
        }




