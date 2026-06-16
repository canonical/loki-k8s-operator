#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import jubilant
import sh
import yaml
from helpers import is_loki_up

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
app_name = METADATA["name"]


def test_deploy_from_local_path(juju: jubilant.Juju, loki_charm, loki_resources):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")
    juju.deploy(loki_charm, app_name, resources=loki_resources, trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )
    assert is_loki_up(juju, app_name)


def test_config_values_are_retained_after_pod_deleted_and_restarted(juju: jubilant.Juju):
    pod_name = f"{app_name}-0"
    model_name = juju.status().model.name

    sh.kubectl.delete.pod(pod_name, namespace=model_name)  # pyright: ignore

    juju.wait(
        lambda status: (
            len(status.apps[app_name].units) > 0
            and jubilant.all_active(status)
            and jubilant.all_agents_idle(status)
        ),
        timeout=15 * 60,
    )
    assert is_loki_up(juju, app_name)
