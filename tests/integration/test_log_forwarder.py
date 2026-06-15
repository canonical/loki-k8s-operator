#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import yaml
from helpers import delete_pod, get_pebble_plan, loki_alerts, loki_rules, oci_image
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(20),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def wait_for_loki_rules(juju: jubilant.Juju, app_name: str) -> dict:
    """Wait for alert rules to be loaded into Loki."""
    rules = loki_rules(juju, app_name)
    if not rules:
        raise ValueError("Alert rules not loaded yet")
    return rules


tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-forwarder-tester/charmcraft.yaml", "workload-image"
    )
}


def test_deploy(juju: jubilant.Juju, loki_charm, loki_resources, log_forwarder_tester_charm):
    juju.deploy(loki_charm, "loki", resources=loki_resources, trust=True)
    juju.deploy(log_forwarder_tester_charm, "log-forwarder-tester", resources=tester_resources)


def test_containers_forward_logs_after_pod_kill(juju: jubilant.Juju):
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )
    juju.integrate("loki", "log-forwarder-tester")
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )

    assert juju.model
    workload_a_plan = get_pebble_plan(juju.model, "log-forwarder-tester", 0, "workload-a")
    workload_b_plan = get_pebble_plan(juju.model, "log-forwarder-tester", 0, "workload-b")
    assert "log-targets" in yaml.safe_load(workload_a_plan)
    assert "log-targets" in yaml.safe_load(workload_b_plan)

    # Delete tester pod
    delete_pod(juju.model, "log-forwarder-tester", 0)
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )

    restarted_workload_a_plan = get_pebble_plan(juju.model, "log-forwarder-tester", 0, "workload-a")
    restarted_workload_b_plan = get_pebble_plan(juju.model, "log-forwarder-tester", 0, "workload-b")
    assert "log-targets" in yaml.safe_load(restarted_workload_a_plan)
    assert "log-targets" in yaml.safe_load(restarted_workload_b_plan)


def test_alerts_are_in_loki(juju: jubilant.Juju):
    """Test basic alerts functionality of Log Forwarder."""
    juju.config("log-forwarder-tester", {"rate": "5"})
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )
    wait_for_loki_rules(juju, "loki")
    rules_response = loki_rules(juju, "loki")
    # Loki rules is a dict of {group_name: [groups]}, where groups is a list of dicts with a "rules" key containing a list of rules.
    # We first flatten this structure to get a list of rules, then check that the expected Juju labels are present in each rule's labels.
    alerts = [
        rule
        for groups in rules_response.values()
        for group in groups
        for rule in group["rules"]
    ]
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
