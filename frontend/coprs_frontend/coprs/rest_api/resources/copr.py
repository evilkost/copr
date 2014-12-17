import json
import flask
from flask import url_for
from flask_restful import Resource, reqparse

from marshmallow import Schema, fields, pprint

from coprs.views.misc import api_login_required
from coprs.logic.coprs_logic import CoprsLogic

from ..util import get_one_safe, json_loads_safe, mm_deserialize


class NewCoprSchema(Schema):
    name = fields.Str(required=True)
    description = fields.Str()
    instructions = fields.Str()

    chroots = fields.List(fields.Str)


class CoprListR(Resource):

    @api_login_required
    def post(self):
        owner = flask.g.user
        new_copr_dict = json_loads_safe(flask.request.data, "")


        result = mm_deserialize(NewCoprSchema(), new_copr_dict)

        return result.data

    def get(self):
        parser = reqparse.RequestParser()

        parser.add_argument('owner', dest='username', type=str)
        parser.add_argument('limit', type=int)
        parser.add_argument('offset', type=int)
        parser.add_argument('id', dest='ids', default=[], type=int, action='append')
        req_args = parser.parse_args()

        kwargs = {}
        for key in ["username", "ids"]:
            if req_args[key]:
                kwargs[key] = req_args[key]

        if "username" in kwargs:
            kwargs["user_relation"] = "owned"

        query = CoprsLogic.get_multiple(
            flask.g.user,
            with_builds=True,
            **kwargs
        )

        if req_args["offset"]:
            query = query.offset(req_args["offset"])

        if req_args["limit"]:
            query = query.limit(req_args["limit"])

        # try:
        coprs_list = query.all()
        # except Exception as error:
        #     import ipdb; ipdb.set_trace()
        #     a = 2

        return {
            "links": {
                "self": url_for(CoprListR.endpoint, **req_args)
            },
            "coprs": [
                {
                    "copr": copr.to_dict(),
                    "link": url_for(CoprR.endpoint,
                                    owner_name=copr.owner.name,
                                    project_name=copr.name),
                }
                for copr in coprs_list
            ]
        }


class CoprR(Resource):

    def get(self, owner_name, project_name):
        parser = reqparse.RequestParser()
        parser.add_argument('show_builds', type=bool, default=True)
        parser.add_argument('show_chroots', type=bool, default=True)
        req_args = parser.parse_args()

        copr = get_one_safe(CoprsLogic.get(flask.g.user, owner_name, project_name),
                            "Copr {}/{} not found".format(owner_name, project_name))
        return {
            "links": {
                "self": url_for(CoprR.endpoint,
                                owner_name=owner_name,
                                project_name=project_name),
                # "chroots":
                # "builds":
            },
            "copr": copr.to_dict()
        }
