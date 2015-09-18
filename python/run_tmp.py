# coding: utf-8

from copr.client_v2.client import CoprClient
from copr.client_v2.entities import ProjectEntity

def main():
    copr_url = "http://copr-fe-dev.cloud.fedoraproject.org"
    client = CoprClient.create_from_params(
        root_url=copr_url,
        login="wczictdaerhmwfxolham",
        token="kxcnwfmleulpnkckzspxxgwhxjolhc"

    )
    client.post_init()

    project = client.projects.get_one(3260)

    print("Project: {} id {}, {}\n {}".format(
        project.name,
        project.id,
        project.description,
        [(x, y.href) for x, y in project._links.items()]
    ))
    # res = project._handle.update(project)

    plist = client.projects.get_list(limit=7)
    for p in plist:
        print(p)
        print(p.get_href_by_name("builds"))


if __name__ == "__main__":
    main()
