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

    loki_app_data_on_requirer_side = await juju_show_unit(
        ops_test,
        "loki-tester/0",
        endpoint="logging",
        related_unit=app_name + "/0",
        app_data_only=True,
    )

    # Output looks like this:
    # {
    #     "opened-ports": [],
    #     "charm": "ch:amd64/focal/grafana-agent-k8s-7",
    #     "leader": True,
    #     "relation-info": [
    #         {
    #             "endpoint": "logging-consumer",
    #             "related-endpoint": "logging",
    #             "application-data": {
    #                 "endpoints": '[{"url": "http://loki-k8s-0...local:3100/loki/api/v1/push"}]',
    #                 "promtail_binary_zip_url": "https://.../promtail-linux-amd64.zip",
    #             },
    #         }
    #     ],
    #     "provider-id": "grafana-agent-k8s-0",
    #     "address": "10.1.50.210",
    # }

    # There is only one "logging" relation in place so blindly taking [0]
    relevant_data = loki_app_data_on_requirer_side["relation-info"][0]["application-data"]
    endpoints = yaml.safe_load(relevant_data["endpoints"])
    promtail_url = relevant_data["promtail_binary_zip_url"]

    # We called juju_show_unit with specific endpoint (relation) name and related unit name, so
    # there should be exactly one url listed.
    assert len(endpoints) == 1

    # "Validate" the push api url
    loki_push_url = endpoints[0]["url"]
    assert loki_push_url.startswith("http")

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
        app_data_only=True,
    )

    # There is only one "logging" relation in place so blindly taking [0]
    endpoints = yaml.safe_load(
        loki_data_on_requirer_side["relation-info"][0]["application-data"]["endpoints"]
    )
    assert len(endpoints) == 3


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
    endpoints = yaml.safe_load(
        loki_data_on_requirer_side["relation-info"][0]["application-data"]["endpoints"]
    )
    assert len(endpoints) == 0
