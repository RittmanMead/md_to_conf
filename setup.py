#!/usr/bin/env python
from setuptools import setup
from pathlib import Path

if Path("version.txt").is_file():
    with open("version.txt") as f:
        version = f.read()
else:
    version = "0.0.0"

version_name = version.strip().lstrip("v")

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="md-to-conf",
    version=version_name,
    description="Markdown to Confluence Cloud Publisher",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Matt Gerega",
    url="https://github.com/spyder007/md_to_conf",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["md_to_conf"],
    install_requires=[
        # NB: Pin these to a more specific version for tap reliability
        "certifi",
        "chardet",
        "idna",
        "Markdown",
        "requests",
        "urllib3",
    ],
    entry_points="""
    [console_scripts]
    md-to-conf=md_to_conf:main
    """,
    packages=["md_to_conf"],
    package_data={},
    include_package_data=False,
)
