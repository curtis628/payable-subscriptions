import sys

from setuptools import find_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="payable-subscriptions",
    version="1.0.5",
    url='https://github.com/curtis628/payable-subscriptions',
    author='Tyler Curtis',
    author_email="tjcurt@gmail.com",
    description="Integrates out-of-the-box payment processing for django-flexible-subscriptions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=['tests*']),
    project_urls={
        'Source code': 'https://github.com/curtis628/payable-subscriptions',
        'Issues': 'https://github.com/curtis628/payable-subscriptions/issues',
    },
    python_requires='>=3.7',
    install_requires=[
        'django>=4.0',
        'django-flexible-subscriptions>=0.15.1',
        'venmo-api>=0.3.1'
    ],
    tests_require=[
        'pytest>=6.0.0',
    ],
    # See http://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Framework :: Django :: 4.1',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: Unix',
    ],
    entry_points={},
)
