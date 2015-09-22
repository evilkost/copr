# coding: utf-8

from collections import Iterable
from marshmallow import Schema, fields
from marshmallow import Schema, fields, validates_schema, ValidationError, validate

# todo: maybe define schemas for Link sets in each indvidual/collection
# class LinkSchema(Schema):
#     href = fields.Str()
#


class EmptySchema(Schema):
    pass


class ProjectSchema(Schema):

    id = fields.Int()
    name = fields.Str()

    owner = fields.Str()
    description = fields.Str()
    instructions = fields.Str()
    homepage = fields.Url(allow_none=True)
    contact = fields.Str(allow_none=True)

    disable_createrepo = fields.Bool(allow_none=True)
    build_enable_net = fields.Bool(allow_none=True)
    last_modified = fields.DateTime(dump_only=True)

    repos = fields.List(fields.Str())


class ProjectChrootSchema(Schema):

    name = fields.Str(load_only=True)
    buildroot_pkgs = fields.List(fields.Str())


    comps = fields.Str(allow_none=True)
    comps_name = fields.Str(allow_none=True)
    comps_len = fields.Int(load_only=True, allow_none=True)
