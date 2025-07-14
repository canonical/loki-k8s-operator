#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import jubilant
import pytest
from pytest_operator.plugin import OpsTest
import yaml
from helpers import get_alertmanager_alerts

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


@pytest.mark.abort_on_fail
async def test_alert_rules_do_forward_to_alertmanager(
    ops_test: OpsTest, loki_charm, loki_tester_charm
):
    """Test basic functionality of Loki push API relation interface."""
    assert ops_test.model
    juju = jubilant.Juju(model=ops_test.model_name)

    juju.model_config({"logging-config": "<root>=WARNING; unit=DEBUG"})

    juju.deploy(loki_charm, "loki", resources=resources, trust=True)
    juju.deploy(loki_tester_charm, "loki-tester")
    juju.deploy("alertmanager-k8s", app="alertmanager", channel="2/edge", trust=True)

    juju.integrate("loki", "loki-tester")
    juju.integrate("loki", "alertmanager")

    juju.wait(jubilant.all_active)

    # Trigger a log message to fire an alert on
    await (
        ops_test.model.applications["loki-tester"]
        .units[0]
        .run_action("log-error", message="Error logged!")
    )
    alerts = await get_alertmanager_alerts(ops_test, "alertmanager", 0, retries=100)
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
