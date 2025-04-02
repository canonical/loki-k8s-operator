#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import sh
import yaml
from helpers import is_loki_up

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
app_name = METADATA["name"]
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


@pytest.mark.abort_on_fail
async def test_deploy_from_local_path(ops_test, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")

    await ops_test.model.deploy(
        loki_charm, application_name=app_name, resources=resources, trust=True
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_config_values_are_retained_after_pod_deleted_and_restarted(ops_test):
    pod_name = f"{app_name}-0"

    sh.kubectl.delete.pod(pod_name, namespace=ops_test.model_name)  # pyright: ignore

    await ops_test.model.block_until(lambda: len(ops_test.model.applications[app_name].units) > 0)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)
