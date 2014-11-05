#!/usr/bin/python

from setuptools import setup

long_description = """Copr is designed to be a lightweight buildsystem that allows contributors
to create packages, put them in repositories, and make it easy for users
to install the packages onto their system. Within the Fedora Project it
is used to allow packagers to create third party repositories.

This part is a backend."""


requires = [
    'PyYAML',
    'ansible',
    'setproctitle',
    'redis',
    'retask',
    'python-daemon',
    'bunch',
    #'copr'
]


__version__ = 1.46
__description__ = "Backend part of the Copr build system"
__author__ = "Copr team"
__author_email__ = "copr-devel@lists.fedorahosted.org"
__url__ = "http://fedorahosted.org/copr/"


setup(
    name='copr_backend',
    version=__version__,
    description=__description__,
    long_description=long_description,
    author=__author__,
    author_email=__author_email__,
    url=__url__,
    license='GPLv2+',
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Topic :: System :: Archiving :: Packaging",
        "Development Status :: 1 - Alpha",
    ],
    install_requires=requires,
    package_dir={'': 'src'},
    packages=['copr_backend'],
    py_modules=['copr_create_repo', 'copr_mockremote'],
    entry_points={
        'console_scripts': [
            'copr_mockremote = copr_mockremote:main',
        ]
    },
    include_package_data=True,
    zip_safe=False,
)
