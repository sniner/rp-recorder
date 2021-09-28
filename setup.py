import sys
from setuptools import setup, find_packages

setup(
    # Requirements
    python_requires=">=3.9",

    # Metadata
    name = "rp-recorder",
    version = "0.1.0",
    author = "Stefan Schönberger",
    author_email = "mail@sniner.dev",
    description = "Shoutcast/Radio Paradise audio stream recorder",

    # Packages
    packages = find_packages(),

    # Dependencies
    install_requires = [
        "urllib3",
        "requests",
        "pyyaml",
    ],
    extras_require = {
        "dev": [
        ],
    },

    # Scripts
    entry_points = {
        "console_scripts": [
            "rp-record = rprecorder.cli.record:main",
            "rp-track = rprecorder.cli.track:main",
        ]
    },

    # Packaging information
    platforms = "any",
)

# vim: set et sw=4 ts=4: