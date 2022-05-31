#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging

import pytest
from helpers import is_loki_up, oci_image

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_ingress_traefik_k8s(ops_test, loki_charm):
    """Test that Loki can be related with the Grafana Agent over remote_write."""
    loki_name = "loki"
    traefik_name = "traefik-ingress"

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources={"loki-image": oci_image("./metadata.yaml", "loki-image")},
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
    await is_loki_up(ops_test, loki_name, 0)

    await ops_test.model.add_relation(traefik_name, f"{loki_name}:ingress")

    # Wait a little more than usual, there are various rounds of relation_changed
    # to be processed.

    await ops_test.model.wait_for_idle(apps=apps, status="active")

    result = await _retrieve_proxied_endpoints(ops_test, traefik_name)
    assert f"{loki_name}/0" in result
    assert result[f"{loki_name}/0"] == {
        "url": f"http://foo.bar:80/{ops_test.model_name}-{loki_name}-0"
    }


@pytest.mark.abort_on_fail
async def test_ingress_traefik_k8s_upscaling_loki(ops_test, loki_charm):
    loki_name = "loki"
    traefik_name = "traefik-ingress"

    scale = 3
    await ops_test.model.applications[loki_name].scale(scale=scale)
    await ops_test.model.wait_for_idle(
        apps=[loki_name], status="active", wait_for_exact_units=scale
    )

    result = await _retrieve_proxied_endpoints(ops_test, traefik_name)

    for u in range(scale):
        assert f"{loki_name}/{u}" in result
        assert result[f"{loki_name}/{u}"] == {
            "url": f"http://foo.bar:80/{ops_test.model_name}-{loki_name}-{u}"
        }
    assert len(result) == scale


@pytest.mark.abort_on_fail
async def test_remove_relation(ops_test, loki_charm):
    loki_name = "loki"
    traefik_name = "traefik-ingress"
    await ops_test.model.applications[loki_name].remove_relation("ingress", traefik_name)

    await ops_test.model.wait_for_idle(apps=[loki_name], status="active", timeout=1000)
    assert await is_loki_up(ops_test, loki_name)

    result = await _retrieve_proxied_endpoints(ops_test, traefik_name)
    assert len(result) == 0


async def _retrieve_proxied_endpoints(ops_test, traefik_application_name):
    traefik_application = ops_test.model.applications[traefik_application_name]
    traefik_first_unit = next(iter(traefik_application.units))
    action = await traefik_first_unit.run_action("show-proxied-endpoints")
    await action.wait()
    result = await ops_test.model.get_action_output(action.id)

    return json.loads(result["proxied-endpoints"])
