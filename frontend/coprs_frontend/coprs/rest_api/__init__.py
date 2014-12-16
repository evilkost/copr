# coding: utf-8

import sqlalchemy.orm.exc
import flask
from flask import jsonify
from flask.ext import restful
from flask.ext.restful import Resource, Api


from ..models import Copr
from coprs.logic.coprs_logic import CoprsLogic

URL_PREFIX = "/api_2.0"


class CoprNotFound(Exception):
    def __init__(self, code, data, *args):
        super(CoprNotFound, self).__init__(*args)
        self.code = code
        self.data = data

    def to_dict(self, *args, **kwargs):
        return {}


class CoprR(Resource):
    def get(self, owner_name, project_name):    
        copr = CoprsLogic.get(flask.g.user, owner_name, project_name).one()
        return {
            "owner": owner_name,
            "project": project_name,
            "raw": copr.to_dict()
        }


class MyApi(Api):
    def handle_error(self, e):

        if isinstance(e, sqlalchemy.orm.exc.NoResultFound ):
            response = {}
            return self.make_response({"e": repr(e)}, 404)


        super(MyApi, self).handle_error(e)


def register_api(app, db):
    api = MyApi(
        app,
        prefix=URL_PREFIX,
        catch_all_404s=True,

    )

    api.add_resource(CoprR, "/copr/<owner_name>/<project_name>")

    @app.errorhandler(CoprNotFound)
    def handle_copr_not_found(error):
        response = jsonify(error.data)
        response.status_code = error.code
        return response
