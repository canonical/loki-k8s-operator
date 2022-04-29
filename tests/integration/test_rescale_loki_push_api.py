#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests how relation data changes with rescaling.

Feature: When the Loki charm is rescaled, all the related charms over loki_push_api need to have
up-to-date information of current (remaining) Loki units.

Scenario:
1. Deploy the charm with one unit.
2. Scale up from one to three units.
3. Scale down to zero units.
"""


import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up, juju_show_unit
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


async def test_setup_env(ops_test: OpsTest, loki_charm, loki_tester_charm):
    """Setup test environment."""
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})

    # GIVEN loki and a loki_push_api requirer charm are deployed
    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm, resources=resources, application_name=app_name, num_units=1
        ),
        ops_test.model.deploy(
            loki_tester_charm,
            application_name="loki-tester",
        ),
    )

    # AND the two charms are related
    await ops_test.model.add_relation(app_name, "loki-tester")
    await ops_test.model.wait_for_idle(status="active", timeout=600)


@pytest.mark.abort_on_fail
async def test_requirer_has_loki_endpoint(ops_test: OpsTest):
    # THEN the requirer has the loki push endpoint URL over relation data.

    related_unit = app_name + "/0"
    loki_app_data_on_requirer_side = await juju_show_unit(
        ops_test,
        "loki-tester/0",
        endpoint="logging",
        related_unit=related_unit,
    )

    # There is only one "logging" relation in place so blindly taking [0]
    relevant_data_endpoint = loki_app_data_on_requirer_side["relation-info"][0]["related-units"][
        related_unit
    ]["data"]
    endpoint = yaml.safe_load(relevant_data_endpoint["endpoint"])

    # "Validate" the push api url
    loki_push_url = endpoint["url"]
    assert loki_push_url.startswith("http")

    relevant_data_promtail = loki_app_data_on_requirer_side["relation-info"][0]["application-data"]
    promtail_url = relevant_data_promtail["promtail_binary_zip_url"]
    # "Validate" promtail url
    assert promtail_url.startswith("http")


@pytest.mark.abort_on_fail
async def test_scale_up_to_three_units(ops_test: OpsTest):
    # WHEN loki is scaled up to three units
    await ops_test.model.applications[app_name].scale(scale=3)
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name, num_units=3)

    # THEN requirer must have all three units' push urls
    loki_data_on_requirer_side = await juju_show_unit(
        ops_test,
        "loki-tester/0",
        endpoint="logging",
    )

    # There is only one "logging" relation in place so blindly taking [0]
    units = loki_data_on_requirer_side["relation-info"][0]["related-units"]
    assert len(units) == 3

    for unit in loki_data_on_requirer_side["relation-info"][0]["related-units"].values():
        endpoint = yaml.safe_load(unit["data"]["endpoint"])["url"]
        assert endpoint.startswith("http")


@pytest.mark.abort_on_fail
async def test_scale_down_to_zero_units(ops_test: OpsTest):
    # WHEN loki is scaled down to zero units
    await ops_test.model.applications[app_name].scale(scale=0)
    await ops_test.model.wait_for_idle(
        apps=[app_name], status="active", timeout=600, wait_for_exact_units=0
    )

    # THEN requirer must have no push urls
    loki_data_on_requirer_side = await juju_show_unit(
        ops_test,
        "loki-tester/0",
        endpoint="logging",
        app_data_only=True,
    )

    # There is only one "logging" relation in place so blindly taking [0]
    assert "related-units" not in loki_data_on_requirer_side["relation-info"][0]
