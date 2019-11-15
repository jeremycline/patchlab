#!/usr/bin/env python

import os
import re

from setuptools import setup, find_packages


here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.rst")) as fd:
    README = fd.read()

with open(os.path.join(here, "patchlab", "__init__.py")) as fd:
    match = re.search('^__version__ = "([^"]+)"$', fd.read(), re.MULTILINE)
    VERSION = match.group(1)


def get_requirements(requirements_file="requirements.txt"):
    """Get the contents of a file listing the requirements.

    Args:
        requirements_file (str): The path to the requirements file, relative
                                 to this file.

    Returns:
        list: the list of requirements, or an empty list if
              ``requirements_file`` could not be opened or read.
    """
    with open(requirements_file) as fd:
        lines = fd.readlines()
    dependencies = []
    for line in lines:
        maybe_dep = line.strip()
        if maybe_dep.startswith("#"):
            # Skip pure comment lines
            continue
        if maybe_dep.startswith("git+"):
            # VCS reference for dev purposes, expect a trailing comment
            # with the normal requirement
            __, __, maybe_dep = maybe_dep.rpartition("#")
        else:
            # Ignore any trailing comment
            maybe_dep, __, __ = maybe_dep.partition("#")
        # Remove any whitespace and assume non-empty results are dependencies
        maybe_dep = maybe_dep.strip()
        if maybe_dep:
            dependencies.append(maybe_dep)
    return dependencies


setup(
    name="patchlab",
    version=VERSION,
    description="A Django application designed to bridge Patchwork to GitLab",
    long_description=README,
    url="https://github.com/jeremycline/patchlab",
    # Possible options are at https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    maintainer="Jeremy Cline",
    maintainer_email="jcline@fedoraproject.org",
    license="GPLv2+",
    platforms=["GNU/Linux"],
    keywords=["patchwork", "gitlab", "django"],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=get_requirements(),
    tests_require=get_requirements(requirements_file="dev-requirements.txt"),
    test_suite="patchlab.tests",
)
