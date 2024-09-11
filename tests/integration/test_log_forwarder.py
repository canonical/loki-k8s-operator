#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import delete_pod, get_pebble_plan, oci_image

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-forwarder-tester/metadata.yaml", "workload-image"
    )
}


@pytest.mark.abort_on_fail
async def test_containers_forward_logs_after_pod_kill(
    ops_test, loki_charm, log_forwarder_tester_charm
):
    loki_app_name = "loki"
    tester_app_name = "log-forwarder-tester"
    app_names = [loki_app_name, tester_app_name]

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
            trust=True,
        ),
        ops_test.model.deploy(
            log_forwarder_tester_charm,
            resources=tester_resources,
            application_name=tester_app_name,
        ),
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    workload_a_plan = await get_pebble_plan(ops_test.model_name, tester_app_name, 0, "workload-a")
    workload_b_plan = await get_pebble_plan(ops_test.model_name, tester_app_name, 0, "workload-b")

    assert "log-targets" in yaml.safe_load(workload_a_plan)
    assert "log-targets" in yaml.safe_load(workload_b_plan)

    # Delete tester pod
    await delete_pod(ops_test.model_name, tester_app_name, 0)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    restarted_workload_a_plan = await get_pebble_plan(
        ops_test.model_name, tester_app_name, 0, "workload-a"
    )
    restarted_workload_b_plan = await get_pebble_plan(
        ops_test.model_name, tester_app_name, 0, "workload-b"
    )

    assert "log-targets" in yaml.safe_load(restarted_workload_a_plan)
    assert "log-targets" in yaml.safe_load(restarted_workload_b_plan)
