#!/usr/bin/env python

import os
import setuptools
import subprocess
import sys


here = os.path.dirname(os.path.realpath(__file__))
about = {}
with open(os.path.join(here, 'fleece', '__about__.py'), 'r') as abt:
    exec(abt.read(), about)


# Add the commit hash to the keywords for sanity.
if any(k in ' '.join(sys.argv).lower() for k in ['upload', 'dist']):
    try:
        current_commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD']).strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    else:
        if current_commit and len(current_commit) == 40:
            about['__keywords__'].append(current_commit[:8])


# pandoc --from=markdown_github --to=rst README.md --output=README.rst
LONG_DESCRIPTION = ''
readme = os.path.join(here, 'README.rst')
if os.path.isfile(readme):
    with open(os.path.join(here, 'README.rst')) as rdme:
        LONG_DESCRIPTION = rdme.read()


INSTALL_REQUIRES = [
    'structlog>=15.3.0',
    'requests>=2.9.1',
]

TESTS_REQUIRE = [
    'coverage>=4.0.3',
    'flake8>=2.5.1',
    'mock>=1.3.0',
    'nose>=1.3.7',
    'pylint>=1.5.4',
]


CLASSIFIERS = [
    'Intended Audience :: Developers',
    'License :: OSI Approved :: Apache Software License',
    'Operating System :: OS Independent',
    'Topic :: Software Development',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7'
]


package_attributes = {
    'author': about['__author__'],
    'author_email': about['__email__'],
    'classifiers': CLASSIFIERS,
    'description': about['__summary__'],
    'install_requires': INSTALL_REQUIRES,
    'keywords': ' '.join(about['__keywords__']),
    'license': about['__license__'],
    'long_description': LONG_DESCRIPTION,
    'name': about['__title__'],
    'packages': setuptools.find_packages(exclude=['tests']),
    'tests_require': TESTS_REQUIRE,
    'url': about['__url__'],
    'version': about['__version__'],
}

setuptools.setup(**package_attributes)
