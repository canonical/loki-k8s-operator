#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up, loki_rules

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}
rules_app = "loki-tester"


@pytest.mark.abort_on_fail
async def test_deploy_charms(ops_test, loki_charm, loki_tester_charm):
    """Deploy Loki.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.deploy(loki_charm, resources=resources, application_name=app_name)

    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert ops_test.model.applications[app_name].units[0].workload_status == "active"

    assert await is_loki_up(ops_test, app_name)

    await asyncio.gather(
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=rules_app,
        ),
    )

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app)

    await ops_test.model.wait_for_idle(apps=[app_name, rules_app], status="active", timeout=1000)

    # verify setup is complete and as expected
    rules = await loki_rules(ops_test, app_name)
    assert bool(rules)


async def test_rule_files_are_retained_after_pod_upgraded(ops_test, loki_charm):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    rules_before_upgrade = await loki_rules(ops_test, app_name)
    logger.debug("upgrade deployed charm with local charm %s", loki_charm)
    await ops_test.model.applications[app_name].refresh(path=loki_charm, resources=resources)

    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)

    assert await is_loki_up(ops_test, app_name)
    rules_after_upgrade = await loki_rules(ops_test, app_name)
    assert rules_after_upgrade == rules_before_upgrade
