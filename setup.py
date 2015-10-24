#!/usr/bin/env python

from setuptools import setup
import os

setup(
    name='spanglass',
    version='0.0.2',
    description='Static site deployment tool',
    install_requires = ['six', 'formic', 'cement', 'boto'],
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
