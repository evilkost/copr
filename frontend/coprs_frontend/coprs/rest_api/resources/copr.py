import base64
import json
import datetime
import flask
from flask import url_for
from flask_restful import Resource, reqparse
import functools

from marshmallow import Schema, fields, pprint

from coprs import db
from coprs.exceptions import DuplicateException
from coprs.logic.complex_logic import ComplexLogic
from coprs.logic.users_logic import UsersLogic

from coprs.logic.coprs_logic import CoprsLogic

from coprs.exceptions import ActionInProgressException, InsufficientRightsException
from .build import BuildListR

from ..exceptions import ObjectAlreadyExists, AuthFailed
from ..util import get_one_safe, json_loads_safe, mm_deserialize

def rest_api_auth_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        apt_login = None
        if "Authorization" in flask.request.headers:
            base64string = flask.request.headers["Authorization"]
            base64string = base64string.split()[1].strip()
            userstring = base64.b64decode(base64string)
            (apt_login, token) = userstring.split(":")
        token_auth = False
        if token and apt_login:
            user = UsersLogic.get_by_api_login(apt_login).first()
            if (user and user.api_token == token and
                    user.api_token_expiration >= datetime.date.today()):

                token_auth = True
                flask.g.user = user
        if not token_auth:
            message = (
                "Login invalid/expired. "
                "Please visit https://copr.fedoraproject.org/api "
                "get or renew your API token.")

            raise AuthFailed(message)
        return f(*args, **kwargs)
    return decorated_function


class CoprSchema(Schema):
    name = fields.Str(required=True)
    description = fields.Str()
    instructions = fields.Str()

    auto_createrepo = fields.Bool()

    chroots = fields.List(fields.Str, required=True)
    repos = fields.List(fields.Str)

    _keys_to_make_object = [
        "description",
        "instructions",
        "auto_createrepo"
    ]

    def make_object(self, data):
        """
        Create kwargs for CoprsLogic.add
        """
        kwargs = dict(
            name=data["name"].strip(),
            repos=" ".join(data.get("repos", [])),
            selected_chroots=data["chroots"],
        )
        for key in self._keys_to_make_object:
            if key in data:
                kwargs[key] = data[key]
        return kwargs


class CoprListR(Resource):

    @rest_api_auth_required
    def post(self):
        """
        Creates new copr
        """
        owner = flask.g.user
        new_copr_dict = json_loads_safe(flask.request.data, "")

        result = mm_deserialize(CoprSchema(), new_copr_dict)
        # todo check that chroots are available
        pprint(result.data)
        try:
            copr = CoprsLogic.add(user=owner, check_for_duplicates=True, **result.data)
            db.session.commit()
        except DuplicateException as error:
            raise ObjectAlreadyExists(data=error)

        return copr.to_dict(), 201

    def get(self):
        """
        Get coprs collection
        :return:
        """
        parser = reqparse.RequestParser()

        parser.add_argument('owner', dest='username', type=str)
        parser.add_argument('limit', type=int)
        parser.add_argument('offset', type=int)
        req_args = parser.parse_args()

        kwargs = {}
        for key in ["username"]:
            if req_args[key]:
                kwargs[key] = req_args[key]

        if "username" in kwargs:

            kwargs["username"] = req_args["username"]
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
                                    owner=copr.owner.name,
                                    project=copr.name),
                }
                for copr in coprs_list
            ]
        }


class CoprR(Resource):

    @rest_api_auth_required
    def delete(self, owner, project):
        copr = get_one_safe(CoprsLogic.get(flask.g.user, owner, project),
                            "Copr {}/{} not found".format(owner, project))
        try:
            ComplexLogic.delete_copr(copr)
        except (ActionInProgressException,
                InsufficientRightsException) as err:
            db.session.rollback()
            raise
        else:
            db.session.commit()

        return None, 204

    def get(self, owner, project):
        parser = reqparse.RequestParser()
        parser.add_argument('show_builds', type=bool, default=True)
        parser.add_argument('show_chroots', type=bool, default=True)
        req_args = parser.parse_args()

        copr = get_one_safe(CoprsLogic.get(flask.g.user, owner, project),
                            "Copr {}/{} not found".format(owner, project))
        return {
            "links": {
                "self": url_for(CoprR.endpoint,
                                owner=owner,
                                project=project),
                # "chroots":
                "builds": url_for(BuildListR.endpoint,
                                  owner=copr.owner.name,
                                  project=copr.name)
            },
            "copr": copr.to_dict()
        }


