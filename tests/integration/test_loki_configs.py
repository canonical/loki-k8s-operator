#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import all_active_idle, is_loki_up, loki_config, loki_services

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
app_name = "loki-k8s"


@pytest.mark.setup
def test_services_running(juju: jubilant.Juju, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")

    juju.deploy(loki_charm, app_name, resources=resources, trust=True)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)
    assert is_loki_up(juju, app_name)

    services = loki_services(juju, app_name)
    assert all(status == "Running" for status in services.values()), "Not all services are running"


def test_retention_configs(juju: jubilant.Juju):
    default_configs = loki_config(juju, app_name)
    assert all(
        [
            default_configs["limits_config"]["retention_period"] == "0s",
            not default_configs["compactor"]["retention_enabled"],
        ]
    )

    juju.config(app_name, {"retention-period": "3"})
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)

    configs_with_retention = loki_config(juju, app_name)
    assert all(
        [
            configs_with_retention["limits_config"]["retention_period"] == "3d",
            configs_with_retention["compactor"]["retention_enabled"],
        ]
    )
