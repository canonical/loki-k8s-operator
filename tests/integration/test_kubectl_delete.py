#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import jubilant
import pytest
import sh
import yaml
from helpers import all_active_idle, is_loki_up

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
app_name = "loki-k8s"


@pytest.mark.juju_setup
def test_deploy_from_local_path(juju: jubilant.Juju, loki_charm):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")

    juju.deploy(loki_charm, app_name, resources=resources, trust=True)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)
    is_loki_up(juju, app_name)



def test_config_values_are_retained_after_pod_deleted_and_restarted(juju: jubilant.Juju):
    pod_name = f"{app_name}-0"

    sh.kubectl.delete.pod(pod_name, namespace=juju.model)  # pyright: ignore

    juju.wait(lambda s: app_name in s.apps and len(s.get_units(app_name)) > 0, timeout=1000)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)
    assert is_loki_up(juju, app_name)
