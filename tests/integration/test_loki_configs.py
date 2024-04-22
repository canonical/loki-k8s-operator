#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up, loki_config, loki_services
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


@pytest.mark.abort_on_fail
async def test_services_running(ops_test: OpsTest, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")

    await ops_test.model.deploy(
        loki_charm, application_name=app_name, resources=resources, trust=True
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)

    services = await loki_services(ops_test, app_name)
    assert all(status == "Running" for status in services.values()), "Not all services are running"


@pytest.mark.abort_on_fail
async def test_retention_configs(ops_test: OpsTest):
    default_configs = await loki_config(ops_test, app_name)
    assert all(
        [
            default_configs["limits_config"]["retention_period"] == "0s",
            not default_configs["compactor"]["retention_enabled"],
        ]
    )

    await ops_test.model.applications[app_name].set_config({"retention-period": "3"})
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)

    configs_with_retention = await loki_config(ops_test, app_name)
    assert all(
        [
            configs_with_retention["limits_config"]["retention_period"] == "3d",
            configs_with_retention["compactor"]["retention_enabled"],
        ]
    )