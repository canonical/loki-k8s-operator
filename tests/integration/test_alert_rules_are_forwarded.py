#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest
from helpers import get_alertmanager_alerts

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
def test_alert_rules_do_forward_to_alertmanager(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    loki_tester_charm,
    cos_channel,
):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    alertmanager_app_name = "alertmanager"

    juju.model_config({"logging-config": "<root>=WARNING; unit=DEBUG"})

    juju.deploy(loki_charm, loki_app_name, resources=loki_resources, trust=True)
    juju.deploy(loki_tester_charm, tester_app_name)
    juju.deploy(
        "ch:alertmanager-k8s",
        alertmanager_app_name,
        channel=cos_channel,
        trust=True,
    )

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    juju.integrate(loki_app_name, tester_app_name)
    juju.integrate(loki_app_name, alertmanager_app_name)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    # Trigger a log message to fire an alert on
    juju.run(f"{tester_app_name}/0", "log-error", {"message": "Error logged!"})
    alerts = get_alertmanager_alerts(juju, "alertmanager", 0, retries=100)
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
