#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest
import pytest_jubilant
from helpers import get_alertmanager_alerts

logger = logging.getLogger(__name__)

resources = pytest_jubilant.get_resources()


def test_alert_rules_do_forward_to_alertmanager(juju: jubilant.Juju, loki_charm, loki_tester_charm, cos_channel):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    alertmanager_app_name = "alertmanager"
    app_names = [loki_app_name, tester_app_name, alertmanager_app_name]

    juju.model_config({"logging-config": "<root>=WARNING; unit=DEBUG"})

    juju.deploy(loki_charm, loki_app_name, resources=resources, trust=True)
    juju.deploy(loki_tester_charm, tester_app_name)
    juju.deploy("ch:alertmanager-k8s", alertmanager_app_name, channel=cos_channel, trust=True)
    juju.wait(lambda s: jubilant.all_active(s, *app_names))

    juju.integrate(loki_app_name, tester_app_name)
    juju.integrate(loki_app_name, alertmanager_app_name)
    juju.wait(lambda s: jubilant.all_active(s, *app_names))

    # Trigger a log message to fire an alert on
    juju.run(f"{tester_app_name}/0", "log-error", params={"message": "Error logged!"})
    alerts = get_alertmanager_alerts(juju, "alertmanager", 0, retries=100)
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
