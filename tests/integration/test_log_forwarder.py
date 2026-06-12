#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import yaml
from helpers import delete_pod, get_pebble_plan, loki_alerts, oci_image

logger = logging.getLogger(__name__)

tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-forwarder-tester/charmcraft.yaml", "workload-image"
    )
}


def test_deploy(juju: jubilant.Juju, loki_charm, loki_resources):
    juju.deploy(loki_charm, "loki", resources=loki_resources, trust=True)
    juju.deploy("flog-k8s", "flog", channel="latest/edge", trust=True)


def test_containers_forward_logs_after_pod_kill(juju: jubilant.Juju):
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )
    juju.integrate("loki", "flog:log-forwarder")
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )

    assert juju.model
    flog_plan = get_pebble_plan(juju.model, "flog", 0, "workload")
    assert "log-targets" in yaml.safe_load(flog_plan)

    # Delete tester pod
    delete_pod(juju.model, "flog", 0)
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=5 * 60,
    )

    restarted_flog_plan = get_pebble_plan(juju.model, "flog", 0, "flog")
    assert "log-targets" in yaml.safe_load(restarted_flog_plan)


def test_alerts_are_in_loki(juju: jubilant.Juju):
    """Test basic alerts functionality of Log Forwarder."""
    alerts = loki_alerts(juju, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
