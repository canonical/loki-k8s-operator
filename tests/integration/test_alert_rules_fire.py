#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import get_alertmanager_alerts, is_loki_up, juju_show_unit, loki_alerts

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


@pytest.mark.abort_on_fail
async def test_alert_rules_do_fire(ops_test, loki_charm, loki_tester_charm):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    app_names = [loki_app_name, tester_app_name]

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
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
        )
    )
    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    # Trigger a log message to fire an alert on
    await ops_test.model.applications[tester_app_name].units[0].run_action(
        "log-error", message="Error logged!"
    )
    alerts = await loki_alerts(ops_test, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )


@pytest.mark.abort_on_fail
async def test_loki_scales_up(ops_test):
    """Make sure Loki endpoints propagate on scaling."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    app_names = [loki_app_name, tester_app_name]

    await ops_test.model.applications[loki_app_name].scale(scale=3)
    await ops_test.model.wait_for_idle(apps=app_names, status="active")
    assert await is_loki_up(ops_test, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on
    await ops_test.model.applications[tester_app_name].units[0].run_action(
        "log-error", message="Error logged!"
    )

    alerts_per_unit = await asyncio.gather(
        loki_alerts(ops_test, "loki", unit_num=0),
        loki_alerts(ops_test, "loki", unit_num=1),
        loki_alerts(ops_test, "loki", unit_num=2),
    )

    for unit_alerts in alerts_per_unit:
        assert all(
            key in alert["labels"].keys()
            for key in ["juju_application", "juju_model", "juju_model_uuid"]
            for alert in unit_alerts
        )


@pytest.mark.abort_on_fail
async def test_scale_down_to_zero_units(ops_test):
    loki_app_name = "loki"
    await ops_test.model.applications[loki_app_name].scale(scale=0)
    await ops_test.model.wait_for_idle(
        apps=[loki_app_name], status="active", timeout=600, wait_for_exact_units=0
    )

    loki_data_on_requirer_side = await juju_show_unit(
        ops_test,
        "loki-tester/0",
        endpoint="logging",
        app_data_only=True,
    )

    assert "related-units" not in loki_data_on_requirer_side["relation-info"][0]

    # FIXME: move the following test to the bundle and end the file here once merged and we can
    # Clean up the model so the next test can run
    await ops_test.model.reset()


@pytest.mark.abort_on_fail
async def test_alert_rules_do_forward_to_alertmanager(ops_test, loki_charm, loki_tester_charm):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    alertmanager_app_name = "alertmanager"
    app_names = [loki_app_name, tester_app_name, alertmanager_app_name]

    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})

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

    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
            and len(ops_test.model.applications[alertmanager_app_name].units) > 0
        )
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

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
