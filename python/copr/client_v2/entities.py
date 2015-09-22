# coding: utf-8

from ..util import UnicodeMixin

from .schemas import ProjectSchema, EmptySchema


class Link(UnicodeMixin):

    def __init__(self, role, href, target_type):
        self.role = role
        self.href = href
        self.target_type = target_type  # not sure if we need this

    def __unicode__(self):
        return u"<Link: role: {}, target type: {}, href: {}".format(
            self.role, self.target_type, self.href)

    @classmethod
    def parse_from_dict(cls, data_dict, map_name_to_role):
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
        return cls(**parsed.data)


class ProjectEntity(Entity):
    """
    :type handle: client_v2.handlers.ProjectHandle
    """

    _schema = ProjectSchema(strict=True)

    def __init__(self, **kwargs):

        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.owner = kwargs.get("owner")
        self.description = kwargs.get("description")
        self.instructions = kwargs.get("instructions")
        self.homepage = kwargs.get("homepage")
        self.contact = kwargs.get("contact")
        self.disable_createrepo = kwargs.get("disable_creatrepo")
        self.build_enable_net = kwargs.get("build_enable_net")
        self.repos = kwargs.get("repos")

    def __unicode__(self):
        return "<Project #{}: {}/{}>".format(self.id, self.owner, self.name)
