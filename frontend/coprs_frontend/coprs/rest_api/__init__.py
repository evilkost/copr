# coding: utf-8
from flask import Response, url_for

from flask_restful import Resource, Api

from coprs.rest_api.exceptions import ApiError
from coprs.rest_api.resources.chroot import ChrootListR, ChrootR
from coprs.rest_api.resources.copr import CoprListR, CoprR


URL_PREFIX = "/api_2.0"


class RootR(Resource):
    def get(self):
        return {
            "links": {
                "self": url_for(RootR.endpoint),
                "coprs": url_for(CoprListR.endpoint),
                "chroots": url_for(ChrootListR.endpoint),
            }
        }


class MyApi(Api):
    # flask-restfull error handling quite buggy right now
    def error_router(self, original_handler, e):
        return original_handler(e)
    # def handle_error(self, e):
    #
    #     if isinstance(e, sqlalchemy.orm.exc.NoResultFound):
    #         return self.make_response(str(e), 404)
    #
    #
    #     super(MyApi, self).handle_error(e)


def register_api(app, db):
    api = MyApi(
    # api = Api(
        app,
        prefix=URL_PREFIX,
        catch_all_404s=True,

    )

    api.add_resource(RootR, "/")
    api.add_resource(CoprListR, "/coprs")
    api.add_resource(CoprR, "/coprs/<owner_name>/<project_name>")

    api.add_resource(ChrootListR, "/chroots")
    api.add_resource(ChrootR, "/chroots/<name>")

    @app.errorhandler(ApiError)
    def handle_api_error(error):
        response = Response(
            response="{}\n".format(error.data),
            status=error.code,
            mimetype="text/plain"
        )
        return response