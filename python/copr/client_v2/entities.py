# coding: utf-8
from ..util import UnicodeMixin

from .schemas import ProjectSchema, EmptySchema, ProjectChrootSchema, BuildSchema, BuildTaskSchema, MockChrootSchema


class Link(UnicodeMixin):
    def __init__(self, role, href, target_type):
        self.role = role
        self.href = href
        self.target_type = target_type  # not sure if we need this

    def __unicode__(self):
        return u"<Link: role: {}, target type: {}, href: {}".format(
            self.role, self.target_type, self.href)

    @classmethod
    def from_dict(cls, data_dict, map_name_to_role):
        """
        {
            "self": {
              "href": "/api_2/projects/2482?show_builds=True&show_chroots=True"
            },
            "chroots": {
              "href": "/api_2/projects/2482/chroots"
            },
            "builds": {
              "href": "/api_2/builds?project_id=2482"
            }
        }

        return
        {
            <entity type> -> Link()
        }
        """
        return {
            role_name:
                cls(role_name, definition["href"], map_name_to_role[role_name])
            for role_name, definition in data_dict.items()
            if role_name in map_name_to_role
        }


class Entity(UnicodeMixin):
    _schema = EmptySchema()

    def __init__(self, **kwargs):
        for field in self._schema.fields.keys():
            setattr(self, field, kwargs.get(field))

    def to_dict(self):
        return self._schema.dump(self).data

    def to_json(self):
        return self._schema.dumps(self).data

    @classmethod
    def from_dict(cls, raw_dict):
        parsed = cls._schema.load(raw_dict)
        return cls(**parsed.data)


class ProjectEntity(Entity):
    _schema = ProjectSchema(strict=True)

    # def __init__(self, **kwargs):
    #     self.id = kwargs["id"]
    #     self.name = kwargs["name"]
    #
    #     self.owner = kwargs["owner"]
    #     self.description = kwargs.get("description")
    #     self.instructions = kwargs.get("instructions")
    #     self.homepage = kwargs.get("homepage")
    #     self.contact = kwargs.get("contact")
    #
    #     self.disable_createrepo = kwargs.get("disable_createrepo")
    #     self.build_enable_net = kwargs.get("build_enable_net")
    #     self.last_modified = kwargs.get("last_modified")
    #
    #     self.repos = kwargs.get("repos", list())

    def __unicode__(self):
        return "<Project #{}: {}/{}>".format(self.id, self.owner, self.name)


class ProjectChrootEntity(Entity):
    _schema = ProjectChrootSchema(strict=True)

    # def __init__(self, **kwargs):
    #     self.name = kwargs["name"]
    #     self.buildroot_pkgs = kwargs.get("buildroot_pkgs", list())
    #
    #     self.comps = kwargs.get("comps")
    #     self.comps_name = kwargs.get("comps_name")
    #     self.comps_len = kwargs.get("comps_len")

    def __unicode__(self):
        return "<Project chroot: {}, additional " \
               "packages: {}, comps size if any: {}>"\
            .format(self.name, self.buildroot_pkgs, self.comps_len,)


class BuildEntity(Entity):
    _schema = BuildSchema(strict=True)

    # def __init__(self, **kwargs):
    #
    #     self.id = kwargs["id"]
    #     self.state = kwargs["state"]
    #
    #     self.submitter = kwargs["submitter"]
    #
    #     self.built_packages = kwargs["built_packages"]
    #
    #

    def __unicode__(self):
        return "<Build #{} state: {}>".format(self.id, self.state)


class BuildTaskEntity(Entity):
    _schema = BuildTaskSchema(strict=True)

    def __unicode__(self):
        return "<Build task #{}-{}, state: {}>".format(
            self.build_id, self.chroot_name, self.state
        )


class MockChrootEntity(Entity):

    _schema = MockChrootSchema(strict=True)

    def __unicode__(self):
        return "<Mock chroot: {} is active: {}>".format(
            self.name, self.is_active
        )
