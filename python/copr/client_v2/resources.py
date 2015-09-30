# coding: utf-8
from collections import Iterable

from ..util import UnicodeMixin

from .common import EntityTypes
from .entities import Link, ProjectEntity, ProjectChrootEntity, BuildEntity, MockChrootEntity
from .schemas import EmptySchema


class IndividualResource(UnicodeMixin):
    """
    :type handle: client_v2.handlers.AbstractHandle or None
    :type response: ResponseWrapper or None
    :type links: (dict of (str, Link)) or None
    """
    _schema = EmptySchema(strict=True)

    def __init__(self, entity, handle=None, response=None, links=None, embedded=None, options=None):
        self._entity = entity
        self._handle = handle
        self._response = response
        self._links = links
        self._embedded = embedded or dict()
        self._options = options or dict()

    def __dir__(self):
        res = list(set(
            dir(self.__class__) + list(self.__dict__.keys())
        ))
        if self._entity:
            res.extend([x for x in dir(self._entity) if not x.startswith("_")])
        return res

    def __getattr__(self, item):
        # import ipdb; ipdb.set_trace()
        if hasattr(self._entity, item):
            return getattr(self._entity, item)
        else:
            raise KeyError(item)

    def __unicode__(self):
        return self._entity.__unicode__()

    def get_href_by_name(self, name):
        """
        :type name: str
        """
        return self._links[name].href


class Root(IndividualResource):

    def __init__(self, response, links, root_url):
        super(Root, self).__init__(entity=None, response=response, links=links)
        self.root_url = root_url

    def get_resource_base_url(self, resource_name):
        """
        :type entity_type: client_v2.common.EntityTypes
        """
        return "{}{}".format(self.root_url, self.get_href_by_name(resource_name))

    @classmethod
    def from_response(cls, response, root_url):
        """
        :type response: ResponseWrapper
        :type root_url: unicode
        """
        data_dict = response.json
        links = Link.from_dict(data_dict["_links"], {
            "self": EntityTypes.ROOT,
            "projects": EntityTypes.PROJECT,
            "builds": EntityTypes.BUILD,
            "build_tasks": EntityTypes.BUILD_TASK,
            "mock_chroots": EntityTypes.MOCK_CHROOT,
        })
        return Root(response=response, links=links, root_url=root_url)


class Build(IndividualResource):
    """
    :type entity: BuildEntity
    :type handle: copr.client_v2.handlers.BuildHandle
    """
    def __init__(self, entity, handle, **kwargs):
        super(Build, self).__init__(entity=entity, handle=handle, **kwargs)
        self._entity = entity
        self._handle = handle

    @classmethod
    def from_response(cls, handle, response, data_dict, options=None):
        links = Link.from_dict(data_dict["_links"], {
            "self": EntityTypes.BUILD,
            "project": EntityTypes.PROJECT,
            "build_tasks": EntityTypes.BUILD_TASK,
        })
        entity = BuildEntity.from_dict(data_dict["build"])
        return cls(entity=entity, handle=handle,
                   response=response, links=links, options=options)

    def get_self(self):
        return self._handle.get_one(self.id)

    def cancel(self):
        return self._handle.cancel(self._entity)

    def delete(self):
        return self._handle.delete(self.id)


class Project(IndividualResource):
    """
    :type entity: ProjectEntity
    :type handle: copr.client_v2.handlers.ProjectHandle
    """
    def __init__(self, entity, handle, **kwargs):
        super(Project, self).__init__(entity=entity, handle=handle, **kwargs)
        self._entity = entity
        self._handle = handle

    def update(self):
        return self._handle.update(self._entity)

    def delete(self):
        return self._handle.delete(self.id)

    def get_self(self):
        return self._handle.get_one(self.id, **self._options)

    def get_project_chroot(self, name):
        handle = self._handle.get_project_chroots_handle()
        return handle.get_one(self, name)

    def get_project_chroot_list(self):
        handle = self._handle.get_project_chroots_handle()
        return handle.get_list(self)

    def enable_project_chroot(self, *args, **kwargs):
        handle = self._handle.get_project_chroots_handle()
        return handle.enable(self, *args, **kwargs)

    # TODO: remove proxy methods on the handle classes
    def create_build_from_file(self, *args, **kwargs):
        """
        See additional options `:py:method:BuildHandle.create_from_file:`
        """
        builds = self._handle.get_builds_handle()
        return builds.create_from_file(self.id, *args, **kwargs)

    @classmethod
    def from_response(cls, handle, response, data_dict, options=None):
        links = Link.from_dict(data_dict["_links"], {
            "self": EntityTypes.PROJECT,
            "builds": EntityTypes.BUILD,
            "chroots": EntityTypes.PROJECT_CHROOT,
        })
        entity = ProjectEntity.from_dict(data_dict["project"])
        # import ipdb; ipdb.set_trace()
        return cls(entity=entity, handle=handle,
                   response=response, links=links, options=options)


class ProjectChroot(IndividualResource):
    """
    :type entity: copr.client_v2.entities.ProjectChrootEntity
    :type handle: copr.client_v2.handlers.ProjectChrootHandle
    """
    def __init__(self, entity, handle, project, **kwargs):
        super(ProjectChroot, self).__init__(entity=entity, handle=handle, **kwargs)
        self._entity = entity
        self._handle = handle
        self._project = project

    @classmethod
    def from_response(cls, handle, response, data_dict, project, options=None):
        links = Link.from_dict(data_dict["_links"], {
            "self": EntityTypes.PROJECT_CHROOT,
            "project": EntityTypes.PROJECT,
        })
        entity = ProjectChrootEntity.from_dict(data_dict["chroot"])
        return cls(entity=entity, handle=handle, project=project,
                   response=response, links=links, options=options)

    def disable(self):
        return self._handle.disable(self._project, self.name)

    def update(self):
        return self._handle.update(self._project, self._entity)


class MockChroot(IndividualResource):
    """
    :type entity: copr.client_v2.entities.MockChrootEntity
    :type handle: copr.client_v2.handlers.MockChrootHandle
    """

    def __init__(self, entity, handle, **kwargs):
        super(MockChroot, self).__init__(
            entity=entity,
            handle=handle,
            **kwargs
        )

    @classmethod
    def from_response(cls, handle, response, data_dict, options=None):
        links = Link.from_dict(data_dict["_links"], {
            "self": EntityTypes.MOCK_CHROOT,
        })
        entity = MockChrootEntity.from_dict(data_dict["chroot"])
        return cls(entity=entity, handle=handle,
                   response=response, links=links, options=options)


class OperationResult(IndividualResource):

    # TODO: app param expected_status=200 and method is_successful() which would compare
    # obtained status with expected one
    def __init__(self, handle, response=None, entity=None, options=None, expected_status=200):
        super(OperationResult, self).__init__(handle=handle, response=response, entity=entity, options=options)
        self.expected_status = expected_status

    @property
    def new_location(self):
        if self._response and \
                self._response.headers and \
                "location" in self._response.headers:
            return self._response.headers["location"]

        return None

    def is_successful(self):
        if self._response and self._response.status_code == self.expected_status:
            return True
        else:
            return False

    def __unicode__(self):
        out = u"<Result: "
        if self._response:
            out += u" status: {}".format(self._response.status_code)
        out += u">"

        return out


class CollectionResource(Iterable, UnicodeMixin):
    """
    :type handle: client_v2.handlers.AbstractHandle or None
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

    def next_page(self):
        limit = self._options.get("limit", 100)
        offset = self._options.get("offset", 0)

        offset += limit
        params = {}
        params.update(self._options)
        params["limit"] = limit
        params["offset"] = offset

        return self._handle.get_list(self, **params)

    def __iter__(self):
        """
        :rtype: Iterable[IndividualResource]
        """
        return iter(self._individuals)

    @classmethod
    def from_response(cls, handle, response, options):
        raise NotImplementedError

    # todo: add classmethod from response


class ProjectsList(CollectionResource):
    """
    :type handle: copr.client_v2.handlers.ProjectHandle
    """

    def __init__(self, handle, **kwargs):
        super(ProjectsList, self).__init__(**kwargs)
        self._handle = handle

    @property
    def projects(self):
        return self._individuals

    @classmethod
    def from_response(cls, handle, response, options):
        data_dict = response.json
        result = ProjectsList(
            handle,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT,
            }),
            individuals=[
                Project.from_response(
                    handle=handle,
                    response=None,
                    data_dict=dict_part,
                )
                for dict_part in data_dict["projects"]
            ],
            options=None
        )
        return result


class BuildList(CollectionResource):
    """
    :type handle: copr.client_v2.handler.BuildHandle
    """
    def __init__(self, handle, **kwargs):
        super(BuildList, self).__init__(**kwargs)
        self._handle = handle

    @property
    def builds(self):
        return self._individuals

    @classmethod
    def from_response(cls, handle, response, options):
        data_dict = response.json
        result = BuildList(
            handle,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.BUILD,
            }),
            individuals=[
                Build.from_response(
                    handle=handle,
                    response=None,
                    data_dict=dict_part,
                )
                for dict_part in data_dict["builds"]
            ]
        )
        return result


class ProjectChrootList(CollectionResource):
    """
    :type handle: copr.client_v2.handlers.ProjectChrootHandle
    """

    def __init__(self, handle, project, **kwargs):
        super(ProjectChrootList, self).__init__(**kwargs)
        self._handle = handle
        self._project = project

    @property
    def chroots(self):
        return self._individuals

    def enable(self, name):
        return self._handle.enable(self._project, name)

    @classmethod
    def from_response(cls, handle, response, project):
        data_dict = response.json
        return ProjectChrootList(
            handle,
            project=project,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT_CHROOT,
            }),
            individuals=[
                ProjectChroot.from_response(
                    handle=handle,
                    response=None,
                    data_dict=dict_part,
                    project=project
                )
                for dict_part in data_dict["chroots"]
            ]
        )


class MockChrootList(CollectionResource):
    """
    :type handle: copr.client_v2.handlers.MockChrootHandle
    """

    def __init__(self, handle, **kwargs):
        super(MockChrootList, self).__init__(**kwargs)
        self._handle = handle

    @property
    def chroots(self):
        return self._individuals
