#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests rescaling.

1. Deploy the charm with three units.
2. Scale down to zero units.
3. Scale up from zero to three units.
4. Add relation, and then scale to zero units.
5. Add another relation, and then scale to three units.
"""


import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


async def test_setup_env(ops_test: OpsTest):
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, loki_charm, loki_tester_charm):
    """Build the charm-under-test and deploy it together with related charms."""
    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm, resources=resources, application_name=app_name, num_units=3
        ),
        ops_test.model.deploy(
            loki_tester_charm,
            application_name="loki-tester",
        ),
        ops_test.model.deploy(
            "ch:alertmanager-k8s",
            application_name="alertmanager",
            channel="edge",
        ),
    )

    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_scale_down_to_zero_units(ops_test: OpsTest):
    await ops_test.model.applications[app_name].scale(scale=0)
    await ops_test.model.wait_for_idle(
        apps=[app_name], status="active", timeout=600, wait_for_exact_units=0
    )


@pytest.mark.abort_on_fail
async def test_scale_back_up_to_three_units(ops_test: OpsTest):
    await ops_test.model.applications[app_name].scale(scale=3)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_add_relation_and_scale_to_zero(ops_test: OpsTest):
    await ops_test.model.add_relation(app_name, "loki-tester")
    await ops_test.model.wait_for_idle(status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name)

    await ops_test.model.applications[app_name].scale(scale=0)
    await ops_test.model.wait_for_idle(
        apps=[app_name], status="active", timeout=600, wait_for_exact_units=0
    )


@pytest.mark.abort_on_fail
async def test_add_relation_and_scale_to_three_units(ops_test: OpsTest):
    await ops_test.model.add_relation(app_name, "alertmanager")
    await ops_test.model.applications[app_name].scale(scale=3)
    await ops_test.model.wait_for_idle(status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name)
