#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import all_active_idle, is_loki_up, loki_rules

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
app_name = "loki-k8s"
rules_app = "loki-tester"


@pytest.mark.juju_setup
def test_deploy_charms(juju: jubilant.Juju, loki_charm, loki_tester_charm):
    """Deploy Loki.

    Assert on the unit status before any relations/configurations take place.
    """
    juju.deploy(loki_charm, app_name, resources=resources, trust=True)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)
    assert is_loki_up(juju, app_name)

    juju.deploy(loki_tester_charm, rules_app)

    # form a relation between loki and the app that provides rules
    juju.integrate(app_name, rules_app)

    juju.wait(lambda s: all_active_idle(s, app_name, rules_app), timeout=1000)

    # verify setup is complete and as expected
    rules = loki_rules(juju, app_name)
    assert bool(rules)


def test_rule_files_are_retained_after_pod_upgraded(juju: jubilant.Juju, loki_charm):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    rules_before_upgrade = loki_rules(juju, app_name)
    logger.debug("upgrade deployed charm with local charm %s", loki_charm)
    juju.refresh(app_name, path=loki_charm, resources=resources)

    juju.wait(lambda s: all_active_idle(s, app_name), timeout=1000)

    assert is_loki_up(juju, app_name)
    rules_after_upgrade = loki_rules(juju, app_name)
    assert rules_after_upgrade == rules_before_upgrade
