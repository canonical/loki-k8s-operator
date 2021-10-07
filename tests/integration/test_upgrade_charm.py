#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
import urllib.request
from pathlib import Path

import pytest
import yaml
from helpers import get_unit_address  # type: ignore[import]

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
# app_name = "am"
app_name = METADATA["name"]

pytestmark = pytest.mark.skip(
    "upgrade charm does not work yet: add_local_charm keeps erroring out with 'ConnectionResetError: [Errno 104] Connection reset by peer'"
)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    log.info("build charm from local source folder")
    local_charm = await ops_test.build_charm(".")
    resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}

    log.info("deploy stable charm from charmhub")
    await ops_test.model.deploy("ch:loki-k8s", application_name=app_name)
    await ops_test.model.wait_for_idle(apps=[app_name], timeout=1000)

    log.info("upgrade deployed charm with local charm %s", local_charm)
    await ops_test.model.applications[app_name].refresh(path=local_charm, resources=resources)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active")


@pytest.mark.abort_on_fail
async def test_alertmanager_is_up(ops_test):
    address = await get_unit_address(ops_test, app_name, 0)
    url = f"http://{address}:3100"
    log.info("am public address: %s", url)

    response = urllib.request.urlopen(
        f"{url}/loki/api/v1/status/buildinfo", data=None, timeout=2.0
    )
    assert response.code == 200
    assert "versionInfo" in json.loads(response.read())
