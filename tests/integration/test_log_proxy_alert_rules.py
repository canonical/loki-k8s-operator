#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import yaml
from helpers import all_active_idle, loki_alerts, oci_image

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-proxy-tester/charmcraft.yaml", "workload-image"
    )
}


def test_alert_rules_do_fire_from_log_proxy(juju: jubilant.Juju, loki_charm, log_proxy_tester_charm):
    """Test basic functionality of Log Proxy."""
    loki_app_name = "loki"
    tester_app_name = "log-proxy-tester"
    app_names = [loki_app_name, tester_app_name]

    juju.deploy(loki_charm, loki_app_name, resources=resources, trust=True)
    juju.deploy(log_proxy_tester_charm, tester_app_name, resources=tester_resources)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    juju.integrate(loki_app_name, tester_app_name)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    # Trigger a log message to fire an alert on
    juju.config(tester_app_name, {"rate": "5"})
    alerts = loki_alerts(juju, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
