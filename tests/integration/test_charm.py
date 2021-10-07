#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
import urllib.request
from pathlib import Path

import pytest
import yaml
from helpers import get_unit_address  # type: ignore[attr-defined]

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm_under_test = await ops_test.build_charm(".")
    resources = {
        "loki-image": METADATA["resources"]["loki-image"]["upstream-source"]
    }
    await ops_test.model.deploy(charm_under_test, resources=resources, application_name="loki")

    # due to a juju bug, occasionally some charms finish a startup sequence with "waiting for IP
    # address"
    # issuing dummy update_status just to trigger an event
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    await ops_test.model.wait_for_idle(apps=["loki"], status="active", timeout=1000)
    assert ops_test.model.applications["loki"].units[0].workload_status == "active"

    # effectively disable the update status from firing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_loki_is_up(ops_test):
    address = await get_unit_address(ops_test, "loki", 0)
    url = f"http://{address}:3100"
    log.info("Loki public address: %s", url)

    response = urllib.request.urlopen(f"{url}/loki/api/v1/status/buildinfo", data=None, timeout=2.0)
    assert response.code == 200
    assert "version" in json.loads(response.read())
