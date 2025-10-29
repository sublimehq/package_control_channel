#!/usr/bin/env python3

"""
This script can be used to detect redirects in package detail URLs.
A redirect typically means a package repository has changed hands.

Note that it requires requests: https://pypi.org/project/requests/
"""

import datetime
import json
import logging
from pathlib import Path
from time import sleep
import sys

import requests

base_dir = Path(__file__).parent.parent
log_path = base_dir / "redirect301_{:%Y-%M-%d_%H-%m-%S}.log".format(datetime.datetime.now())

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(message)s")
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(level=logging.DEBUG)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler(log_path)
file_handler.setLevel(level=logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

for path in sorted(Path(base_dir, "repository").glob("*.json")):
    if path.name == "dependencies.json":
        continue
    logger.debug("Processing '{!s}'".format(path))

    with path.open('r', encoding="utf-8") as f:
        packages_text = f.read()
        packages = json.loads(packages_text)["packages"]

    for package in packages:
        link = package["details"]
        try:
            r = requests.head(link, allow_redirects=False)
            if r.status_code == 301:
                new_link = requests.head(link, allow_redirects=True).url
                if link == new_link:
                    logger.warning("Redirected to same URL: {}".format(link))
                else:
                    logger.info("Found 301: \"{}\" -> \"{}\"".format(link, new_link))
                    packages_text = packages_text.replace(link, new_link)
            else:
                logger.debug("No change for \"{}\"".format(link))

        except Exception:
            logger.exception("Exception on {!r}".format(link))

        sleep(0.1)

    with path.open('w', encoding="utf-8") as f:
        f.write(packages_text)
