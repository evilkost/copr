# coding: utf-8
from abc import abstractmethod, ABCMeta

from .common import EntityTypes
from .entities import Link, ProjectChrootEntity
from .resources import Project, OperationResult, ProjectsList, ProjectChroot, ProjectChrootList, Build, BuildList


class AbstractHandle(object):
    """
    :param client: Should be used only to access other handlers
    :type client: copr.client_v2.client.HandlersProvider
    :type nc: copr.client_v2.net_client.NetClient
    """
    __metaclass__ = ABCMeta

    def __init__(self, client, nc, root_url):
        self.client = client
        self.nc = nc
        self.root_url = root_url

    @abstractmethod
    def get_base_url(self, *args, **kwargs):
        pass


class BuildHandle(AbstractHandle):
    def __init__(self, client, nc, root_url, builds_href):
        super(BuildHandle, self).__init__(client, nc, root_url)
        self.builds_href = builds_href
        self._base_url = "{}{}".format(self.root_url, builds_href)

    def get_base_url(self):
        return self._base_url

    def get_one(self, build_id):
        """
        :type project_id: int
        """

        options = {"build_id": build_id}
        url = "{}/{}".format(self.get_base_url(), build_id)
        response = self.nc.request(url)
        return Build.from_response(
            handle=self,
            response=response,
            data_dict=response.json,
            options=options,
        )

    def get_list(self, project_id=None, owner=None, limit=None, offset=None):
        """
        :param owner:
        :param project_id:
        :param limit:
        :param offset:
        :rtype: BuildList
        """
        options = {
            "project_id": project_id,
            "owner": owner,
            "limit": limit,
            "offset": offset
        }

        response = self.nc.request(self.get_base_url(), query_params=options)
        data_dict = response.json
        result = BuildList(
            self,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.BUILD,
            }),
            individuals=[
                Build.from_response(
                    handle=self,
                    response=None,
                    data_dict=dict_part,
                )
                for dict_part in data_dict["builds"]
            ]
        )
        return result

    def cancel(self, build_entity):
        """
        :type build_entity: copr.client_v2.entities.BuildEntity
        """
        build_id = build_entity.id
        build_entity.state = "canceled"

        url = "{}/{}".format(self.get_base_url(), build_id)
        response = self.nc.request(url, data=build_entity.to_json(), method="PUT", do_auth=True)
        return OperationResult(self, response)

    def delete(self, build_id):
        url = "{}/{}".format(self.get_base_url(), build_id)
        response = self.nc.request(url, method="delete", do_auth=True)
        return OperationResult(self, response)


class ProjectHandle(AbstractHandle):

    def __init__(self, client, nc, root_url, projects_href):
        super(ProjectHandle, self).__init__(client, nc, root_url)
        self.projects_href = projects_href
        self._base_url = "{}{}".format(self.root_url, projects_href)

    def get_base_url(self):
        return self._base_url

    def get_list(self, search_query=None, owner=None, name=None, limit=None, offset=None):
        """
        :param search_query:
        :param owner:
        :param name:
        :param limit:
        :param offset:
        :rtype: ProjectsList
        """
        options = {
            "search_query": search_query,
            "owner": owner,
            "name": name,
            "limit": limit,
            "offset": offset
        }

        response = self.nc.request(self.get_base_url(), query_params=options)
        data_dict = response.json
        result = ProjectsList(
            self,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT,
            }),
            individuals=[
                Project.from_response(
                    handle=self,
                    response=None,
                    data_dict=dict_part,
                )
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
        # import ipdb; ipdb.set_trace()
        url = "{}/{}".format(self.get_base_url(), project_id)
        response = self.nc.request(url, query_params=query_params)
        return Project.from_response(
            handle=self,
            response=response,
            data_dict=response.json,
            options=query_params
        )

    def update(self, project_entity):
        """
        :type project_entity: ProjectEntity
        """
        url = "{}/{}".format(self.get_base_url(), project_entity.id)
        data = project_entity.to_json()

        response = self.nc.request(url, method="put", data=data, do_auth=True)
        return OperationResult(self, response)

    def delete(self, project_id):
        url = "{}/{}".format(self.get_base_url(), project_id)
        response = self.nc.request(url, method="delete", do_auth=True)
        return OperationResult(self, response)

    def get_project_chroot(self, project, name):
        """
        :type project: copr.client_v2.resources.Project
        :param str name: chroot name
        :rtype: copr.client_v2.resources.ProjectChroot
        """
        return self.client.project_chroots.get_one(project, name)

    def get_project_chroot_list(self, project):
        """
        :type project: copr.client_v2.resources.Project
        """
        return self.client.project_chroots.get_list(project)

    def enable_chroot(self, project, *args, **kwargs):
        """
        :type project: copr.client_v2.resources.Project
        """
        return self.client.project_chroots.enable(project, *args, **kwargs)


class ProjectChrootHandle(AbstractHandle):

    def get_base_url(self, project):
        """
        :type project: copr.client_v2.resources.Project
        """
        return "{}{}".format(self.root_url, project.get_href_by_name("chroots"))

    def get_one(self, project, name):
        """
        :type project: copr.client_v2.resources.Project
        :param str name: chroot name
        """

        url = "{}/{}".format(self.get_base_url(project), name)
        response = self.nc.request(url)

        return ProjectChroot.from_response(
            handle=self,
            response=response,
            data_dict=response.json,
            project=project,
        )

    def get_list(self, project):
        """
        :type project: copr.client_v2.resources.Project
        """
        response = self.nc.request(self.get_base_url(project))
        data_dict = response.json
        return ProjectChrootList(
            self,
            project=project,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT_CHROOT,
            }),
            individuals=[
                ProjectChroot.from_response(
                    handle=self,
                    response=None,
                    data_dict=dict_part,
                    project=project
                )
                for dict_part in data_dict["chroots"]
            ]
        )

    def disable(self, project, name):
        """
        :type project: copr.client_v2.resources.Project
        :param str name: chroot name to disable
        """
        url = "{}/{}".format(self.get_base_url(project), name)
        response = self.nc.request(url, method="delete", do_auth=True)
        return OperationResult(self, response)

    def enable(self, project, name, buildroot_pkgs=None):
        """
        :type project: copr.client_v2.resources.Project
        """

        new_entity = ProjectChrootEntity.constructor(
            name=name,
            buildroot_pkgs=buildroot_pkgs or list()
        )
        response = self.nc.request(
            self.get_base_url(project),
            method="POST",
            data=new_entity.to_json(),
            do_auth=True
        )
        return OperationResult(self, response)

    def update(self, project, chroot_entity):
        """
        :type project: copr.client_v2.resources.Project
        :type chroot_entity: copr.client_v2.entities.ProjectChrootEntity
        """
        url = "{}/{}".format(self.get_base_url(project), chroot_entity.name)
        response = self.nc.request(
            url,
            method="PUT",
            data=chroot_entity.to_json(),
            do_auth=True
        )
        return OperationResult(self, response)
