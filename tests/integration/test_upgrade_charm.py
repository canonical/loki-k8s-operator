#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests loki upgrade with and without relations present.

1. Deploy the charm under test _from charmhub_.
2. Refresh with locally built charm.
3. Add all supported relations.
4. Refresh with locally built charm.
5. Add unit and refresh again (test multi unit upgrade with relations).
"""

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
app_name = METADATA["name"]
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


async def test_setup_env(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_upgrade_edge_with_local_in_isolation(ops_test: OpsTest, loki_charm):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    logger.debug("deploy charm from charmhub")
    assert ops_test.model
    await ops_test.model.deploy(
        f"ch:{app_name}",
        application_name=app_name,
        channel="edge",
        trust=True,
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)

    logger.debug("upgrade deployed charm with local charm %s", loki_charm)
    application = ops_test.model.applications[app_name]
    assert application
    await application.refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_upgrade_local_with_local_with_relations(ops_test: OpsTest, loki_charm):
    assert ops_test.model
    # Deploy related apps
    app_names = [app_name, "am", "grafana"]
    await asyncio.gather(
        ops_test.model.deploy(
            "ch:alertmanager-k8s",
            application_name="am",
            channel="edge",
            trust=True,
        ),
        ops_test.model.deploy(
            "ch:grafana-k8s",
            application_name="grafana",
            channel="edge",
            trust=True,
        ),
    )

    # Relate apps
    await asyncio.gather(
        ops_test.model.add_relation(app_name, "am"),
        ops_test.model.add_relation(app_name, "grafana:grafana-source"),
    )
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=60
    )

    # Refresh from path
    application = ops_test.model.applications[app_name]
    assert application
    await application.refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=60
    )
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_upgrade_with_multiple_units(ops_test: OpsTest, loki_charm):
    assert ops_test.model
    app_names = [app_name, "am", "grafana"]
    application = ops_test.model.applications[app_name]
    assert application
    # Add unit
    await application.scale(scale_change=1)
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=60
    )

    # Refresh from path
    await application.refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=60
    )

    assert await is_loki_up(ops_test, app_name, num_units=2)
