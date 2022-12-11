import sys

from setuptools import find_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="venmo-subscriptions",
    version="1.0.001",
    url='https://github.com/curtis628/venmo-subscriptions',
    author='Tyler Curtis',
    author_email="tjcurt@gmail.com",
    description="A subscription-management system integrated with Venmo requests and payments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["*.tests"]),
    package_data={ "": ["*.txt"], },

    # See http://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Framework :: Django :: 4.1',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: Unix',
    ],
    entry_points={},
)
