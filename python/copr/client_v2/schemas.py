# coding: utf-8

from collections import Iterable
from marshmallow import Schema, fields, post_load
from marshmallow import Schema, fields, validates_schema, ValidationError, validate

# todo: maybe define schemas for Link sets in each indvidual/collection
# class LinkSchema(Schema):
#     href = fields.Str()
#
from copr.util import UnicodeMixin


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

    name = fields.Str()
    buildroot_pkgs = fields.List(fields.Str())

    comps = fields.Str(allow_none=True)
    comps_name = fields.Str(allow_none=True)
    comps_len = fields.Int(load_only=True, allow_none=True)


class BuiltPackage(UnicodeMixin):

    def __init__(self, name, version):
        self.name = name
        self.version = version

    def __unicode__(self):
        return u"{} {}".format(self.name, self.version)


class BuiltPackageSchema(Schema):

    name = fields.Str()
    version = fields.Str()

    # @post_load
    def make_object(self, data):
        return BuiltPackage(**data)


class BuildSchema(Schema):
    
    id = fields.Int(load_only=True)
    state = fields.Str()

    submitter = fields.Str(load_only=True)

    built_packages = fields.Nested(BuiltPackageSchema, many=True, load_only=True, allow_none=True)

    package_version = fields.Str(load_only=True, allow_none=True)
    package_name = fields.Str(load_only=True, allow_none=True)

    repos = fields.List(fields.Str(), load_only=True)

    submitted_on = fields.Int(load_only=True)
    started_on = fields.Int(load_only=True, allow_none=True)
    ended_on = fields.Int(load_only=True, allow_none=True)

    enable_net = fields.Bool(load_only=True)

    source_type = fields.Str(load_only=True)
    source_metadata = fields.Raw(load_only=True)


class BuildTaskSchema(Schema):
    
    state = fields.Str()
    started_on = fields.Int(load_only=True)
    ended_on = fields.Int(load_only=True)
    git_hash = fields.Str(load_only=True)
    chroot_name = fields.Str(load_only=True)
    build_id = fields.Int(load_only=True)

    result_dir_url = fields.Str(load_only=True)


class MockChrootSchema(Schema):

    name = fields.Str(load_only=True)
    os_release = fields.Str(load_only=True)
    os_version = fields.Str(load_only=True)
    arch = fields.Str(load_only=True)
    is_active = fields.Bool(load_only=True)
