# coding: utf-8

#from copr.client_v2.client import CoprClient
# from copr.client_v2.entities import ProjectEntity

from copr import create_client2_from_params

def main():
    copr_url = "http://copr-fe-dev.cloud.fedoraproject.org"
    client = create_client2_from_params(
        root_url=copr_url,
        login="wczictdaerhmwfxolham",
        token="kxcnwfmleulpnkckzspxxgwhxjolhc"
    )

    def pp(project):
        print("Project: {} id {}, {}\n {}\n{}".format(
            project.name,
            project.id,
            project.description,
            project.repos,
            [(x, y.href) for x, y in project._links.items()]
        ))

    def t1():
        project = client.projects.get_one(2262)
        #
        pp(project)

    # res = project.update()
    # print(res)
    #
    def t3(project):
        p = project.get_self()
        pp(p)

    def t2():
        plist = client.projects.get_list(limit=20)
        for p in plist:
            #print(p)
            #print(p.get_href_by_name("builds"))
            pp(p)
            print("==")
            print("==")
            print("==")



    # t1()
    t2()




if __name__ == "__main__":
    main()
