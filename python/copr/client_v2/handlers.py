# coding: utf-8

from .common import EntityTypes
from .entities import Link
from .resources import Project, OperationResult, ProjectsList, ProjectChroot, ProjectChrootList


class AbstractHandle(object):
    """
    :type nc: copr.client_v2.net_client.NetClient
    """
    def __init__(self, nc, root_url, base_url, ):

        self.nc = nc
        self.root_url = root_url
        self.base_url = base_url


class ProjectHandle(AbstractHandle):

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
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT,
                "builds": EntityTypes.BUILD,
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

        url = "{}/{}".format(self.base_url, project_id)
        response = self.nc.request(url, query_params=query_params)
        return Project.from_response(
            handle=self,
            response=response,
            data_dict=response.json,
            options=query_params
        )

    def get_project_chroot_handle(self, project):
        """
        :type project: copr.client_v2.resources.Project
        """
        base_url = "{}{}".format(self.root_url, project.get_href_by_name("chroots"))
        return ProjectChrootHandle(self.nc, self.root_url, base_url)

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


class ProjectChrootHandle(AbstractHandle):

    def get_one(self, name):
        """
        :type project: copr.client_v2.resources.Project
        :param str name: chroot name
        """

        url = "{}/{}".format(self.base_url, name)
        response = self.nc.request(url)

        return ProjectChroot.from_response(
            handle=self,
            response=response,
            data_dict=response.json,
        )

    def get_list(self):
        response = self.nc.request(self.base_url)
        data_dict = response.json
        return ProjectChrootList(
            self,
            response=response,
            links=Link.from_dict(data_dict["_links"], {
                "self": EntityTypes.PROJECT_CHROOT,
            }),
            individuals=[
                ProjectChroot.from_response(
                    handle=self,
                    response=None,
                    data_dict=dict_part
                )
                for dict_part in data_dict["chroots"]
            ]
        )

    def disable(self, name):
        pass

    def enable(self, name):
        pass

    def update(self, project_chroot):
        """
        :type project_chroot: copr.client_v2.entities.ProjectChrootEntity
        """
        pass
