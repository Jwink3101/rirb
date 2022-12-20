#!/usr/bin/env python
import sys

# This shouldn't be needed since I have python_requires set but just in case:
if sys.version_info < (3, 8):
    raise ValueError("Must use python >= 3.8")

import rirb

from setuptools import setup

setup(
    name="rirb",
    packages=["rirb"],
    long_description=open("readme.md").read(),
    entry_points={"console_scripts": ["rirb=rirb.cli:cli"],},
    version=rirb.__version__,
    description="Reverse Incremental Rclone Backup",
    url="https://github.com/Jwink3101/rirb/",
    author="Justin Winokur",
    author_email="Jwink3101@@users.noreply.github.com",
    license="MIT",
    python_requires=">=3.8",
)
