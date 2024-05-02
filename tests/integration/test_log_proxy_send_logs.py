#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import Path

import pytest
import yaml
from helpers import generate_log_file, loki_endpoint_request, oci_image

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-proxy-tester/metadata.yaml", "workload-image"
    )
}


@pytest.mark.abort_on_fail
async def test_check_both_containers_send_logs(ops_test, loki_charm, log_proxy_tester_charm):
    loki_app_name = "loki"
    tester_app_name = "log-proxy-tester"
    app_names = [loki_app_name, tester_app_name]

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
            trust=True,
        ),
        ops_test.model.deploy(
            log_proxy_tester_charm,
            resources=tester_resources,
            application_name=tester_app_name,
        ),
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    # Generate log files in the containers
    await generate_log_file(
        ops_test.model_name, tester_app_name, 0, "workload-a", "/tmp/worload-a-1.log"
    )
    await generate_log_file(
        ops_test.model_name, tester_app_name, 0, "workload-a", "/tmp/worload-a-2.log"
    )
    await generate_log_file(
        ops_test.model_name, tester_app_name, 0, "workload-b", "/tmp/worload-b.log"
    )

    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    series = await loki_endpoint_request(ops_test, loki_app_name, "loki/api/v1/series", 0)
    data_series = json.loads(series)["data"]

    found = 0
    for data in data_series:
        if (
            data["container"] in ["workload-a", "workload-b"]
            and data["juju_application"] == tester_app_name
            and data["filename"]
            in [
                "/tmp/worload-a-1.log",
                "/tmp/worload-a-2.log",
                "/tmp/worload-b.log",
            ]
        ):
            found += 1

    # there might be more data series (charm logging).
    assert found == 3
