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

import jubilant
import pytest
import yaml
from helpers import is_loki_up, loki_config

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
V11_APP_NAME = f'v11-{METADATA["name"]}'
V12_APP_NAME = f'v12-{METADATA["name"]}'
V13_APP_NAME = f'v13-{METADATA["name"]}'
LOKI_UPGRADED = "loki-v11-v12-v13"

resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


def test_setup_env(juju: jubilant.Juju):
    juju.model_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.xfail
def test_deploy_from_charmhub_v11_and_upgrade_to_v12_to_v13(
    juju: jubilant.Juju, loki_charm, cos_channel
):
    """Deploy from Charmhub (v11 schema) and upgrade to v12."""
    deploy_charm_from_charmhub_v11(juju, LOKI_UPGRADED, cos_channel)
    upgrade_charm_from_charmhub_v12(juju, LOKI_UPGRADED, loki_charm, cos_channel)
    verify_upgrade_success(juju, LOKI_UPGRADED, False, "v12")

    # Here we upgrade again to ensure config is persisted and won't be overwritten with any weird values
    upgrade_charm_from_charmhub_v12(juju, LOKI_UPGRADED, loki_charm, cos_channel)
    verify_upgrade_success(juju, LOKI_UPGRADED, False, "v12")

    upgrade_charm_with_local_charm_v13(juju, LOKI_UPGRADED, loki_charm)
    verify_upgrade_success(juju, LOKI_UPGRADED, False, "v13", True)


@pytest.mark.xfail
def test_deploy_and_upgrade_v13_locally(juju: jubilant.Juju, loki_charm):
    """Deploy from a local charm (v13 schema) and upgrade locally."""
    deploy_local_charm_v13(juju, V13_APP_NAME, loki_charm)
    upgrade_charm_with_local_charm_v13(juju, V13_APP_NAME, loki_charm)
    verify_upgrade_success(juju, V13_APP_NAME, True, "v13")

    # Here we upgrade again to ensure config is persisted and won't be overwritten with any weird values
    upgrade_charm_with_local_charm_v13(juju, V13_APP_NAME, loki_charm)
    verify_upgrade_success(juju, V13_APP_NAME, True, "v13")


def deploy_charm_from_charmhub_v11(juju: jubilant.Juju, app_name: str, cos_channel: str):
    """Deploy the charm from Charmhub."""
    logger.debug("Deploying charm from Charmhub")
    juju.deploy(
        "ch:loki-k8s",
        app_name,
        channel=cos_channel,
        revision=140,
        trust=True,
    )
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )


def upgrade_charm_from_charmhub_v12(
    juju: jubilant.Juju, app_name: str, loki_charm, cos_channel: str
):
    """Upgrade the deployed charm with the local charm."""
    logger.debug("Upgrading deployed charm with local charm %s", loki_charm)
    juju.cli("refresh", app_name, f"--channel={cos_channel}")
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )


def deploy_local_charm_v13(juju: jubilant.Juju, app_name: str, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")
    juju.deploy(loki_charm, app_name, resources=resources, trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )


def upgrade_charm_with_local_charm_v13(juju: jubilant.Juju, app_name: str, loki_charm):
    """Upgrade the deployed charm with the local charm."""
    logger.debug("Upgrading deployed charm with local charm %s", loki_charm)
    juju.cli("refresh", app_name, f"--path={loki_charm}")
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )


def verify_upgrade_success(
    juju: jubilant.Juju,
    app_name: str,
    is_fresh_installation: bool,
    version: str = "v13",
    after_tomorrow: bool = False,
):
    """Verify that the upgrade was successful."""
    assert is_loki_up(juju, app_name)
    post_upgrade_config = loki_config(juju, app_name)
    tsdb_schema_configs = post_upgrade_config["schema_config"]["configs"]
    days = 2 if after_tomorrow else 1
    expected_from = (
        (datetime.date.today()).strftime("%Y-%m-%d")
        if is_fresh_installation
        else (datetime.date.today() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    )
    for config in tsdb_schema_configs:
        if config["schema"] == version:
            assert config["store"] == "tsdb"
            assert config["from"] == expected_from
