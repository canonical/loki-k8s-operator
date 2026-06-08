#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import is_loki_up, loki_rules

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
app_name = METADATA["name"]
rules_app = "loki-tester"


@pytest.mark.abort_on_fail
def test_deploy_charms(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    loki_tester_charm,
):
    """Deploy Loki.

    Assert on the unit status before any relations/configurations take place.
    """
    juju.deploy(loki_charm, app_name, resources=loki_resources, trust=True)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )

    assert is_loki_up(juju, app_name)

    juju.deploy(loki_tester_charm, rules_app)

    # form a relation between loki and the app that provides rules
    juju.integrate(app_name, rules_app)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )

    # verify setup is complete and as expected
    rules = loki_rules(juju, app_name)
    assert bool(rules)


def test_rule_files_are_retained_after_pod_upgraded(juju: jubilant.Juju, loki_charm, loki_resources):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    rules_before_upgrade = loki_rules(juju, app_name)
    logger.debug("upgrade deployed charm with local charm %s", loki_charm)
    juju.cli("refresh", app_name, f"--path={loki_charm}")

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
        delay=5,
    )

    assert is_loki_up(juju, app_name)
    rules_after_upgrade = loki_rules(juju, app_name)
    assert rules_after_upgrade == rules_before_upgrade
