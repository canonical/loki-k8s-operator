#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests loki upgrade to validate schema migration from v11/boltdb to v12/tsdb.

Test Scenarios:
1. Deploy from Charmhub with revision 140 using v11/boltdb, then upgrade to local charm with v12/tsdb.
2. Deploy locally with v12/tsdb, then upgrade locally to validate configuration persistence.
"""

import datetime
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up, loki_config
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
V11_APP_NAME = f'v11-{METADATA["name"]}'
V12_APP_NAME = f'v12-{METADATA["name"]}'
V13_APP_NAME = f'v13-{METADATA["name"]}'
LOKI_UPGRADED = "loki-v11-v12-v13"

resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


async def test_setup_env(ops_test: OpsTest):
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_deploy_from_charmhub_v11_and_upgrade_to_v12_to_v13(ops_test: OpsTest, loki_charm):
    """Deploy from Charmhub (v11 schema) and upgrade to v12."""
    await deploy_charm_from_charmhub_v11(ops_test, LOKI_UPGRADED)
    await upgrade_charm_from_charmhub_v12(ops_test, LOKI_UPGRADED, loki_charm)
    await verify_upgrade_success(ops_test, LOKI_UPGRADED, False, "v12")

    # Here we upgrade again to ensure config is persisted and won't be overwritten with any weird values
    await upgrade_charm_from_charmhub_v12(ops_test, LOKI_UPGRADED, loki_charm)
    await verify_upgrade_success(ops_test, LOKI_UPGRADED, False, "v12")

    await upgrade_charm_with_local_charm_v13(ops_test, LOKI_UPGRADED, loki_charm)
    await verify_upgrade_success(ops_test, LOKI_UPGRADED, False, "v13")


@pytest.mark.abort_on_fail
async def test_deploy_and_upgrade_v13_locally(ops_test: OpsTest, loki_charm):
    """Deploy from a local charm (v13 schema) and upgrade locally."""
    await deploy_local_charm_v13(ops_test, V13_APP_NAME, loki_charm)
    await upgrade_charm_with_local_charm_v13(ops_test, V13_APP_NAME, loki_charm)
    await verify_upgrade_success(ops_test, V13_APP_NAME, True, "v13")

    # Here we upgrade again to ensure config is persisted and won't be overwritten with any weird values
    await upgrade_charm_with_local_charm_v13(ops_test, V13_APP_NAME, loki_charm)
    await verify_upgrade_success(ops_test, V13_APP_NAME, True, "v13")


async def deploy_charm_from_charmhub_v11(ops_test: OpsTest, app_name):
    """Deploy the charm from Charmhub."""
    logger.debug("Deploying charm from Charmhub")
    await ops_test.model.deploy(
        "ch:loki-k8s",
        application_name=app_name,
        channel="edge",
        revision=140,
        trust=True,
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)


async def upgrade_charm_from_charmhub_v12(ops_test: OpsTest, app_name, loki_charm):
    """Upgrade the deployed charm with the local charm."""
    logger.debug("Upgrading deployed charm with local charm %s", loki_charm)
    await ops_test.model.applications[app_name].refresh(channel="stable", revision=151)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)


async def deploy_local_charm_v13(ops_test: OpsTest, app_name, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")
    await ops_test.model.deploy(
        loki_charm, application_name=app_name, resources=resources, trust=True
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)


async def upgrade_charm_with_local_charm_v13(ops_test: OpsTest, app_name, loki_charm):
    """Upgrade the deployed charm with the local charm."""
    logger.debug("Upgrading deployed charm with local charm %s", loki_charm)
    await ops_test.model.applications[app_name].refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)


async def verify_upgrade_success(
    ops_test: OpsTest, app_name, is_fresh_installation: bool, version: str = "v13"
):
    """Verify that the upgrade was successful."""
    positions = {"v11": 0, "v12": 1, "v13": 2}
    assert await is_loki_up(ops_test, app_name)
    post_upgrade_config = await loki_config(ops_test, app_name)
    tsdb_schema_configs = post_upgrade_config["schema_config"]["configs"][positions[version]]

    expected_from = (
        (datetime.date.today()).strftime("%Y-%m-%d")
        if is_fresh_installation
        else (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    )
    assert tsdb_schema_configs["store"] == "tsdb"
    assert tsdb_schema_configs["schema"] == version
    assert tsdb_schema_configs["from"] == expected_from
