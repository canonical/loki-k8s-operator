#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest
import requests
from helpers import get_unit_address, loki_endpoint_request
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

LOKI = "loki"
GRAFANA = "grafana"
PROMETHEUS = "prometheus"


class AddressNotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)


@pytest.mark.xfail
def test_deploy_and_relate_charms(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    cos_channel,
):
    """Test that Prometheus can be related with the Grafana Agent over remote_write."""
    juju.deploy(loki_charm, LOKI, resources=loki_resources, trust=True)
    juju.deploy("grafana-k8s", GRAFANA, channel=cos_channel, trust=True)
    juju.deploy("prometheus-k8s", PROMETHEUS, channel=cos_channel, trust=True)

    juju.integrate(LOKI, PROMETHEUS)
    juju.integrate(PROMETHEUS, f"{GRAFANA}:grafana-source")
    juju.integrate(GRAFANA, f"{LOKI}:grafana-dashboard")

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )


@pytest.mark.xfail
def test_metrics_are_available(juju: jubilant.Juju):
    metrics = loki_endpoint_request(juju, LOKI, "metrics", 0)
    assert len(metrics) > 0


@pytest.mark.xfail
def test_query_metrics_from_prometheus(juju: jubilant.Juju):
    address = get_unit_address(juju, PROMETHEUS, 0)
    url = f"http://{address}:9090/api/v1/query"
    params = {"query": f"up{{juju_application='{LOKI}'}}"}
    try:
        response = requests.get(url, params=params)
        assert response.json()["status"] == "success"
        assert len(response.json()["data"]["result"]) == 2
    except requests.exceptions.RequestException:
        assert False


@pytest.mark.xfail
def test_dashboard_exists(juju: jubilant.Juju):
    address = get_unit_address(juju, GRAFANA, 0)
    result = juju.run(f"{GRAFANA}/0", "get-admin-password")
    pw = result.results["admin-password"]
    url = f"http://{address}:3000/api/dashboards/tags"
    auth = HTTPBasicAuth("admin", pw)
    params = {"tag": LOKI}
    try:
        response = requests.get(url, auth=auth, params=params)
        assert response.json()
    except requests.exceptions.RequestException:
        assert False
