#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import asyncio
import json
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


@pytest.mark.abort_on_fail
async def test_ingress_traefik_k8s(ops_test, loki_charm):
    """Test that Prometheus can be related with the Grafana Agent over remote_write."""
    loki_name = "loki"
    traefik_name = "traefik-ingress"

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_name,
        ),
        ops_test.model.deploy(
            "traefik-k8s",
            application_name=traefik_name,
            channel="edge",
            config={
                "routing_mode": "path",
                "external_hostname": "foo.bar",
            },
        ),
    )

    apps = [loki_name, traefik_name]
    await ops_test.model.wait_for_idle(apps=apps, status="active")
    assert await is_loki_up(ops_test, loki_name)
    await ops_test.model.add_relation(traefik_name, f"{loki_name}:ingress-per-unit")

    # Wait a little more than usual, there are various rounds of relation_changed
    # to be processed.

    await ops_test.model.wait_for_idle(apps=apps, status="active")

    result = await _retrieve_proxied_endpoints(ops_test, traefik_name)
    assert f"{loki_name}/0" in result
    assert result[f"{loki_name}/0"] == {
        "url": f"http://foo.bar:80/{ops_test.model_name}-{loki_name}-0"
    }


async def _retrieve_proxied_endpoints(ops_test, traefik_application_name):
    traefik_application = ops_test.model.applications[traefik_application_name]
    traefik_first_unit = next(iter(traefik_application.units))
    action = await traefik_first_unit.run_action("show-proxied-endpoints")
    await action.wait()
    result = await ops_test.model.get_action_output(action.id)
    return json.loads(result["proxied-endpoints"])
