#!/usr/bin/env python

from setuptools import setup, find_packages


# FIXME add dependencies (nose)
setup(
    name='taskpile',
    version='0.1',
    description='Simple single-user job queue management system.',
    author='Jan Gosmann',
    author_email='jan@hyper-world.de',
    # url= ... TODO
    packages=find_packages(),
    scripts=['bin/taskpile'])
