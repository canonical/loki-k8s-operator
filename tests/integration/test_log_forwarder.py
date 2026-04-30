#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import all_active_idle, delete_pod, get_pebble_plan, loki_alerts, oci_image

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-forwarder-tester/charmcraft.yaml", "workload-image"
    )
}


@pytest.mark.juju_setup
def test_containers_forward_logs_after_pod_kill(juju: jubilant.Juju, loki_charm, log_forwarder_tester_charm):
    loki_app_name = "loki"
    tester_app_name = "log-forwarder-tester"
    app_names = [loki_app_name, tester_app_name]

    juju.deploy(loki_charm, loki_app_name, resources=resources, trust=True)
    juju.deploy(log_forwarder_tester_charm, tester_app_name, resources=tester_resources)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    juju.integrate(loki_app_name, tester_app_name)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    workload_a_plan = get_pebble_plan(juju.model, tester_app_name, 0, "workload-a")
    workload_b_plan = get_pebble_plan(juju.model, tester_app_name, 0, "workload-b")

    assert "log-targets" in yaml.safe_load(workload_a_plan)
    assert "log-targets" in yaml.safe_load(workload_b_plan)

    # Delete tester pod
    delete_pod(juju.model, tester_app_name, 0)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    restarted_workload_a_plan = get_pebble_plan(juju.model, tester_app_name, 0, "workload-a")
    restarted_workload_b_plan = get_pebble_plan(juju.model, tester_app_name, 0, "workload-b")

    assert "log-targets" in yaml.safe_load(restarted_workload_a_plan)
    assert "log-targets" in yaml.safe_load(restarted_workload_b_plan)


def test_alert_rules_fire(juju: jubilant.Juju, loki_charm, log_forwarder_tester_charm):
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
