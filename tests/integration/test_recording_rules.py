#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
from helpers import is_loki_up, loki_rules, prometheus_query
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(20),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def wait_for_loki_rules(juju: jubilant.Juju, app_name: str) -> dict:
    rules = loki_rules(juju, app_name)
    if not rules:
        raise ValueError("Alert rules not loaded yet")
    return rules


def test_recording_rules_remote_write_to_prometheus(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    loki_tester_charm,
    cos_channel,
):
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    prom_app_name = "prom"

    juju.deploy(loki_charm, loki_app_name, resources=loki_resources, trust=True)
    juju.deploy("ch:prometheus-k8s", prom_app_name, channel=cos_channel, trust=True)
    juju.deploy(loki_tester_charm, tester_app_name)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    is_loki_up(juju, loki_app_name)

    juju.integrate(f"{loki_app_name}:send-remote-write", f"{prom_app_name}:receive-remote-write")
    juju.integrate(loki_app_name, tester_app_name)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    rules = wait_for_loki_rules(juju, loki_app_name)
    assert rules, "recording rules not loaded into Loki"

    juju.run(f"{tester_app_name}/0", "log-error", {"message": "Error logged!"})

    results = prometheus_query(juju, prom_app_name, "loki_tester_errors_total")
    assert results, "recording rule metric not found in Prometheus"
    assert results[0]["metric"]["__name__"] == "loki_tester_errors_total"
