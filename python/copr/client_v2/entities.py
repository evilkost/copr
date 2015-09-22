# coding: utf-8

from ..util import UnicodeMixin

from .schemas import ProjectSchema, EmptySchema, ProjectChrootSchema


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

    def to_dict(self):
        return self._schema.dump(self)

    def to_json(self):
        return self._schema.dumps(self)

    @classmethod
    def from_dict(cls, raw_dict):
        parsed = cls._schema.load(raw_dict)
        obj = cls()
        for field, value in parsed.data.items():
            setattr(obj, field, value)
        return obj


class ProjectEntity(Entity):

    _schema = ProjectSchema(strict=True)

    def __unicode__(self):
        return "<Project #{}: {}/{}>".format(self.id, self.owner, self.name)


class ProjectChrootEntity(Entity):

    _schema = ProjectChrootSchema(strict=True)

    def __unicode__(self):
        return "<Project chroot: {}, additional " \
               "packages: {}, comps size if any: {}>".format(
            self.name,
            self.buildroot_pkgs,
            self.comps_len,
        )
