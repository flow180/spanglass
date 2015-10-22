#!/usr/bin/env python

from setuptools import setup

setup(
    name='spanglass',
    version='0.0.1',
    description='Static site deployment tool',
    platforms='Platform Independent',
    author='Charlie Wolf',
    author_email='charlie@wolf.is',
    url='http://github.com/charliewolf/spanglass',
    packages=[
        'spanglass',
    ],
    entry_points = {
        'console_scripts': ['spanglass=spanglass.main:main']
    }
)
