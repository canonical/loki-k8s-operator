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
from helpers import IPAddressWorkaround, is_loki_up
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


async def test_setup_env(ops_test: OpsTest):
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_upgrade_edge_with_local_in_isolation(ops_test: OpsTest, loki_charm):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    async with IPAddressWorkaround(ops_test):
        logger.debug("deploy charm from charmhub")
        await ops_test.model.deploy(f"ch:{app_name}", application_name=app_name, channel="edge")
        await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)

        logger.debug("upgrade deployed charm with local charm %s", loki_charm)
        await ops_test.model.applications[app_name].refresh(path=loki_charm, resources=resources)
        await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
        assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_refresh_with_relations(ops_test: OpsTest, loki_charm):
    # Deploy related apps
    await asyncio.gather(
        ops_test.model.deploy("ch:alertmanager-k8s", application_name="am", channel="edge"),
        ops_test.model.deploy("ch:grafana-k8s", application_name="grafana", channel="edge"),
    )

    # Relate apps
    await asyncio.gather(
        ops_test.model.add_relation(app_name, "am"),
        ops_test.model.add_relation(app_name, "grafana"),
    )

    # Refresh from path
    await ops_test.model.applications[app_name].refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_upgrade_with_multiple_units(ops_test: OpsTest, loki_charm):
    num_units = 2
    await ops_test.model.applications[app_name].scale(scale=num_units)
    await ops_test.model.wait_for_idle(status="active", timeout=1000)

    # Refresh from path
    await ops_test.model.applications[app_name].refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(status="active", timeout=1000)

    for unit_num in range(num_units):
        assert await is_loki_up(ops_test, app_name, unit_num)
