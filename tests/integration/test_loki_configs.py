#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest
import pytest_jubilant
from helpers import is_loki_up, loki_config, loki_services

logger = logging.getLogger(__name__)

resources = pytest_jubilant.get_resources()
app_name = "loki-k8s"


@pytest.mark.abort_on_fail
def test_services_running(juju: jubilant.Juju, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")

    juju.deploy(loki_charm, app_name, resources=resources, trust=True)
    juju.wait(lambda s: jubilant.all_active(s, app_name), timeout=1000)
    assert is_loki_up(juju, app_name)

    services = loki_services(juju, app_name)
    assert all(status == "Running" for status in services.values()), "Not all services are running"


@pytest.mark.abort_on_fail
def test_retention_configs(juju: jubilant.Juju):
    default_configs = loki_config(juju, app_name)
    assert all(
        [
            default_configs["limits_config"]["retention_period"] == "0s",
            not default_configs["compactor"]["retention_enabled"],
        ]
    )

    juju.config(app_name, {"retention-period": "3"})
    juju.wait(lambda s: jubilant.all_active(s, app_name), timeout=1000)

    configs_with_retention = loki_config(juju, app_name)
    assert all(
        [
            configs_with_retention["limits_config"]["retention_period"] == "3d",
            configs_with_retention["compactor"]["retention_enabled"],
        ]
    )
