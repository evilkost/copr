# coding: utf-8
import json

import sqlalchemy.orm.exc
from .exceptions import ObjectNotFoundError, MalformedRequest


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
