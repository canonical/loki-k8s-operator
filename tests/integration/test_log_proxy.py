#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from helpers import loki_alerts, oci_image

logger = logging.getLogger(__name__)

resources = {"loki-image": oci_image("./metadata.yaml", "loki-image")}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-proxy-tester/metadata.yaml", "workload-image"
    )
}

loki_app_name = "loki"
tester_app_name = "log-proxy-tester"


@pytest.mark.abort_on_fail
async def test_alert_rules_do_fire(ops_test, loki_charm, log_proxy_tester_charm):
    """Test basic functionality of Log Proxy."""
    app_names = [loki_app_name, tester_app_name]

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
        ),
        ops_test.model.deploy(
            log_proxy_tester_charm,
            resources=tester_resources,
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
    await ops_test.model.applications[tester_app_name].set_config({"rate": "5"})
    alerts = await loki_alerts(ops_test, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
