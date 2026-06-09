#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest
import yaml
from helpers import delete_pod, get_pebble_plan, loki_alerts, oci_image

logger = logging.getLogger(__name__)

tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-forwarder-tester/charmcraft.yaml", "workload-image"
    )
}


def test_containers_forward_logs_after_pod_kill(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    log_forwarder_tester_charm,
):
    loki_app_name = "loki"
    tester_app_name = "log-forwarder-tester"

    juju.deploy(loki_charm, loki_app_name, resources=loki_resources, trust=True)
    juju.deploy(log_forwarder_tester_charm, tester_app_name, resources=tester_resources)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    juju.integrate(loki_app_name, tester_app_name)
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    model_name = juju.status().model.name
    workload_a_plan = get_pebble_plan(model_name, tester_app_name, 0, "workload-a")
    workload_b_plan = get_pebble_plan(model_name, tester_app_name, 0, "workload-b")

    assert "log-targets" in yaml.safe_load(workload_a_plan)
    assert "log-targets" in yaml.safe_load(workload_b_plan)

    # Delete tester pod
    delete_pod(model_name, tester_app_name, 0)
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    restarted_workload_a_plan = get_pebble_plan(model_name, tester_app_name, 0, "workload-a")
    restarted_workload_b_plan = get_pebble_plan(model_name, tester_app_name, 0, "workload-b")

    assert "log-targets" in yaml.safe_load(restarted_workload_a_plan)
    assert "log-targets" in yaml.safe_load(restarted_workload_b_plan)


def test_alert_rules_fire(juju: jubilant.Juju):
    """Test basic alerts functionality of Log Forwarder."""
    tester_app_name = "log-forwarder-tester"

    # Trigger a log message to fire an alert on
    juju.config(tester_app_name, {"rate": "5"})
    alerts = loki_alerts(juju, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
