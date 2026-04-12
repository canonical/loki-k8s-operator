#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests loki upgrade with and without relations present.

1. Deploy the charm under test _from charmhub_.
2. Refresh with locally built charm.
3. Add all supported relations.
4. Refresh with locally built charm.
5. Add unit and refresh again (test multi unit upgrade with relations).
"""

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import all_active_idle, is_loki_up

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
app_name = "loki-k8s"


@pytest.mark.setup
def test_setup_env(juju: jubilant.Juju):
    juju.model_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


def test_upgrade_edge_with_local_in_isolation(juju: jubilant.Juju, loki_charm, cos_channel):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    logger.debug("deploy charm from charmhub")
    juju.deploy(app_name, app_name, channel=cos_channel, trust=True)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)

    logger.debug("upgrade deployed charm with local charm %s", loki_charm)
    juju.refresh(app_name, path=loki_charm)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)
    assert is_loki_up(juju, app_name)



def test_upgrade_local_with_local_with_relations(juju: jubilant.Juju, loki_charm, cos_channel):
    # Deploy related apps
    juju.deploy("alertmanager-k8s", "am", channel=cos_channel, trust=True)
    juju.deploy("grafana-k8s", "grafana", channel=cos_channel, trust=True)
    app_names = [app_name, "am", "grafana"]

    # Relate apps
    juju.integrate(app_name, "am")
    juju.integrate(app_name, "grafana:grafana-source")
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    # Refresh from path
    juju.refresh(app_name, path=loki_charm)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)
    assert is_loki_up(juju, app_name)



def test_upgrade_with_multiple_units(juju: jubilant.Juju, loki_charm):
    app_names = [app_name, "am", "grafana"]
    status = juju.status()
    current_units = len(status.get_units(app_name))
    # Add unit
    juju.cli("scale-application", app_name, str(current_units + 1))
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    # Refresh from path
    juju.refresh(app_name, path=loki_charm)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    assert is_loki_up(juju, app_name, num_units=current_units + 1)
