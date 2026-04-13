#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import all_active_idle, generate_log_file, loki_endpoint_request, oci_image

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

loki_app_name = "loki"
tester_app_name = "log-proxy-tester"


@pytest.mark.juju_setup
def test_setup(juju: jubilant.Juju, loki_charm, log_proxy_tester_charm):
    app_names = [loki_app_name, tester_app_name]

    juju.deploy(loki_charm, loki_app_name, resources=resources, trust=True)
    juju.deploy(log_proxy_tester_charm, tester_app_name, resources=tester_resources)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    # Generate log files in the containers
    generate_log_file(juju.model, tester_app_name, 0, "workload-a", "/tmp/worload-a-1.log")
    generate_log_file(juju.model, tester_app_name, 0, "workload-a", "/tmp/worload-a-2.log")
    generate_log_file(juju.model, tester_app_name, 0, "workload-b", "/tmp/worload-b.log")

    juju.integrate(loki_app_name, tester_app_name)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)


@pytest.mark.work
def test_series_found(juju: jubilant.Juju):
    series = loki_endpoint_request(juju, loki_app_name, "loki/api/v1/series", 0)
    data_series = json.loads(series)["data"]

    found = 0
    for data in data_series:
        # filter out the series we generated from those written by charm logging
        if (
            data.get("container") in ["workload-a", "workload-b"]
            and data["juju_application"] == tester_app_name
            and data["filename"]
            in [
                "/tmp/worload-a-1.log",
                "/tmp/worload-a-2.log",
                "/tmp/worload-b.log",
            ]
        ):
            found += 1

    assert found == 3
