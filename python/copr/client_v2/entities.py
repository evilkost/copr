# coding: utf-8

from collections import Iterable
import json

from client_v2.common import EntityTypes
from .net_client import NetClient, ResponseWrapper


class Link(object):

    def __init__(self, role, href, target_type):
        self.role = role
        self.href = href
        self.target_type = target_type

    def __unicode__(self):
        return u"<Link: role: {}, target type: {}, href: {}".format(
            self.role, self.target_type, self.href)

    def __str__(self):
        return self.__unicode__()

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


class Individual(object):
    """
    :type handle: AbstractHandle or None
    :type response: ResponseWrapper
    :type links: (dict of (str, Link)) or None
    """

    def __init__(self, handle=None, response=None, links=None, data=None, embedded=None, options=None):
        self._handle = handle
        self._response = response
        self._links = links
        self._data = data
        self._embedded = embedded or dict()
        self._options = options or dict()

    def get_href_by_name(self, name):
        """
        :type name: str
        """
        return self._links[name].href

    def to_json(self):
        return "null"


class Collection(Iterable):
    """
    :type handle: AbstractHandle or None
    :type response: ResponseWrapper
    :type links: (dict of (str, Link)) or None
    """

    def __init__(self, handle=None, response=None, links=None, individuals=None, options=None):
        self._handle = handle
        self._response = response
        self._links = links
        self._options = options or dict()
        self._individuals = individuals

    def get_href_by_name(self, name):
        """
        :type name: str
        """
        return self._links[name].href

    def __iter__(self):
        """
        :rtype: Iterable[Individual]
        """
        return iter(self._individuals)


class ProjectsList(Collection):
    """
    :type handle: ProjectHandle
    """

    # def __iter__(self):
    #     """
    #     :rtype: Iterable[ProjectEntity]
    #     """
    #     return super(ProjectsList, self).__iter__()

    def __init__(self, handle, **kwargs):
        super(ProjectsList, self).__init__(**kwargs)
        self._handle = handle

    @property
    def projects(self):
        return self._individuals

    def next_page(self):
        limit = self._options.get("limit", 100)
        offset = self._options.get("offset", 0)

        offset += limit
        params = {}
        params.update(self._options)
        params["limit"] = limit
        params["offset"] = offset

        return self._handle.get_list(self, **params)


class OperationResult(Individual):

    def __init__(self, handle, response=None, data=None, new_location=None, options=None):
        super(OperationResult, self).__init__(handle, response=response, data=data, options=options)
        self.new_location = new_location


class RootEntity(Individual):

    def __init__(self, response, links, root_url):
        super(RootEntity, self).__init__(response=response, links=links)
        self.root_url = root_url

    def get_resource_base_url(self, resource_name):
        """
        :type entity_type: client_v2.common.EntityTypes
        """
        return "{}{}".format(self.root_url, self.get_href_by_name(resource_name))


# TODO: replace with marshmallow
class ProjectEntity(Individual):
    """
    :type handle: ProjectHandle
    """
    def __init__(self, handle, **kwargs):
        super(ProjectEntity, self).__init__( **kwargs)
        self._handle = handle

        self.id = self._data.get("id")
        self.name = self._data.get("name")
        self.owner = self._data.get("owner")
        self.description = self._data.get("description")
        self.instructions = self._data.get("instructions")
        self.homepage = self._data.get("homepage")
        self.contact = self._data.get("contact")
        self.disable_createrepo = self._data.get("disable_creatrepo")
        self.build_enable_net = self._data.get("build_enable_net")
        self.repos = self._data.get("repos")

    def to_json(self):
        # todo: replace with marshmallow
        to_dump = {}
        for key in self._data.keys():
            to_dump[key] = getattr(self, key)
        return json.dumps(to_dump)

    def update(self):
        self._handle.update(self)

    def delete(self):
        self._handle.delete(self.id)

    def __unicode__(self):
        return "<Project #{}: {}/{}>".format(self.id, self.owner, self.name)

    def __str__(self):
        return self.__unicode__()


def parse_root(response, root_url):
    """
    :type response: ResponseWrapper
    :type root_url: unicode
    """
    data_dict = response.json
    links = Link.parse_from_dict(data_dict["_links"], {
        "self": EntityTypes.ROOT,
        "projects": EntityTypes.PROJECT,
        "builds": EntityTypes.BUILD,
        "build_tasks": EntityTypes.BUILD_TASK,
        "mock_chroots": EntityTypes.MOCK_CHROOT,
    })
    return RootEntity(response=response, links=links, root_url=root_url)


def parse_project(handle, response, data_dict, options=None):
    links = Link.parse_from_dict(data_dict["_links"], {
        "self": EntityTypes.PROJECT,
        "builds": EntityTypes.BUILD,
    })
    return ProjectEntity(handle, response=response, links=links, data=data_dict["project"], options=options)


class AbstractHandle(object):
    pass


class ProjectHandle(AbstractHandle):
    """
    :type nc: NetClient
    """
    def __init__(self, nc, base_url):

        self.nc = nc
        self.base_url = base_url

    def get_list(self, search_query=None, owner=None, name=None, limit=None, offset=None):
        """
        :param search_query:
        :param owner:
        :param name:
        :param limit:
        :param offset:
        :rtype: ProjectsList
        """
        options = {}
        if limit:
            options["limit"] = limit
        # todo: add other

        response = self.nc.request(self.base_url, query_params=options)
        data_dict = response.json
        result = ProjectsList(
            self,
            response=response,
            links=Link.parse_from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT,
                "builds": EntityTypes.BUILD,
            }),
            individuals=[
                parse_project(self, response, data_dict=dict_part)
                for dict_part in data_dict["projects"]
            ],
            options=None
        )
        return result

    def get_one(self, project_id, show_builds=False, show_chroots=False):
        """
        :type project_id: int
        """
        query_params = {
            "show_builds": show_builds,
            "show_chroots": show_chroots
        }

        url = "{}/{}".format(self.base_url, project_id)
        response = self.nc.request(url, query_params=query_params)
        return parse_project(self, response, data_dict=response.json, options=query_params)

    def update(self, project):
        """
        :type project: ProjectEntity
        """
        url = "{}/{}".format(self.base_url, project.id)
        data = project.to_json()

        response = self.nc.request(url, method="put", data=data, do_auth=True)
        return OperationResult(self, response)

    def delete(self, project_id):
        url = "{}/{}".format(self.base_url, project_id)
        response = self.nc.request(url, method="delete", do_auth=True)
        return OperationResult(self, response)
