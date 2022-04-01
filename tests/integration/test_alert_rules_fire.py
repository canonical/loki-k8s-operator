#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import get_alertmanager_alerts

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


@pytest.mark.abort_on_fail
async def test_alert_rules_do_raise_fire(ops_test, loki_charm, loki_tester_charm):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    alertmanager_app_name = "alertmanager"
    app_names = [loki_app_name, tester_app_name, alertmanager_app_name]

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
        ),
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=tester_app_name,
        ),
        ops_test.model.deploy(
            "ch:alertmanager-k8s",
            application_name=alertmanager_app_name,
            channel="edge",
        ),
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
            and len(ops_test.model.applications[alertmanager_app_name].units) > 0
        )
    )
    await asyncio.gather(
        ops_test.model.add_relation(loki_app_name, tester_app_name),
        ops_test.model.add_relation(loki_app_name, alertmanager_app_name),
    )
    await ops_test.model.wait_for_idle(
        apps=[loki_app_name, tester_app_name, alertmanager_app_name], status="active"
    )

    # Trigger a log message to fire an alert on
    await ops_test.model.applications[tester_app_name].units[0].run_action(
        "log-error", message="Error logged!"
    )
    alerts = await get_alertmanager_alerts(ops_test, "alertmanager", 0, retries=100)
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
