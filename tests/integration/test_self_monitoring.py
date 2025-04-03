#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import requests
import yaml
from helpers import get_unit_address, loki_endpoint_request
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

LOKI = "loki"
GRAFANA = "grafana"
PROMETHEUS = "prometheus"
METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


class AddressNotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)


@pytest.mark.xfail
async def test_deploy_and_relate_charms(ops_test, loki_charm):
    """Test that Prometheus can be related with the Grafana Agent over remote_write."""
    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=LOKI,
            trust=True,
        ),
        ops_test.model.deploy(
            "grafana-k8s",
            application_name=GRAFANA,
            channel="edge",
            trust=True,
        ),
        ops_test.model.deploy(
            "prometheus-k8s",
            application_name=PROMETHEUS,
            channel="edge",
            trust=True,
        ),
    )

    await ops_test.model.add_relation(LOKI, PROMETHEUS)
    await ops_test.model.add_relation(PROMETHEUS, f"{GRAFANA}:grafana-source")
    await ops_test.model.add_relation(GRAFANA, f"{LOKI}:grafana-dashboard")
    apps = [LOKI, GRAFANA, PROMETHEUS]
    await ops_test.model.wait_for_idle(apps=apps, status="active")


@pytest.mark.xfail
async def test_metrics_are_available(ops_test):
    metrics = await loki_endpoint_request(ops_test, LOKI, "metrics", 0)
    assert len(metrics) > 0


@pytest.mark.xfail
async def test_query_metrics_from_prometheus(ops_test):
    address = await get_unit_address(ops_test, PROMETHEUS, 0)
    url = f"http://{address}:9090/api/v1/query"
    params = {"query": f"up{{juju_application='{LOKI}'}}"}
    try:
        response = requests.get(url, params=params)
        assert response.json()["status"] == "success"
        assert len(response.json()["data"]["result"]) == 2
    except requests.exceptions.RequestException:
        assert False


@pytest.mark.xfail
async def test_dashboard_exists(ops_test):
    address = await get_unit_address(ops_test, GRAFANA, 0)
    pw_action = (
        await ops_test.model.applications[GRAFANA].units[0].run_action("get-admin-password")
    )
    pw_action = await pw_action.wait()
    pw = pw_action.results["admin-password"]
    url = f"http://{address}:3000/api/dashboards/tags"
    auth = HTTPBasicAuth("admin", pw)
    params = {"tag": LOKI}
    try:
        response = requests.get(url, auth=auth, params=params)
        assert response.json()
    except requests.exceptions.RequestException:
        assert False
