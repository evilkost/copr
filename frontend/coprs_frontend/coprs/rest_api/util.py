# coding: utf-8
import json

import sqlalchemy.orm.exc
from .exceptions import ObjectNotFoundError, MalformedRequest

from flask import Response, url_for, Blueprint


def bp_url_for(endpoint, *args, **kwargs):
    """
        Prepend endpoing with dot
    :param endpoint:
    :param args:
    :param kwargs:
    :return:
    """

    return url_for(".{}".format(endpoint), *args, **kwargs)


def get_one_safe(query, data_on_error=None):
    try:
        return query.one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise ObjectNotFoundError(data_on_error)


def json_loads_safe(raw, data_on_error=None):
    try:
        return json.loads(raw)
    except ValueError:
        raise MalformedRequest(data_on_error or
                               "Failed to deserialize json string")


def mm_deserialize(schema, obj_dict):
    result = schema.load(obj_dict)
    if result.errors:
        raise MalformedRequest(data=result.errors)
    # import ipdb; ipdb.set_trace()
    return result
