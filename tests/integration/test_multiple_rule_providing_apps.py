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
rules_app2 = "loki-tester2"
rules_app3 = "loki-tester3"
rules_after_relation = None


@pytest.mark.abort_on_fail
async def test_deploy(ops_test, loki_charm):
    """Deploy Loki and ensure it doesn't have any rules yet.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.deploy(
        loki_charm,
        resources=resources,
        application_name=app_name,
        trust=True,
    )

    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert ops_test.model.applications[app_name].units[0].workload_status == "active"

    assert await is_loki_up(ops_test, app_name)

    rules_before_relation = await loki_rules(ops_test, app_name)
    assert len(rules_before_relation) == 0


@pytest.mark.abort_on_fail
async def test_first_relation_one_alert_rule(ops_test, loki_tester_charm):
    await asyncio.gather(
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=rules_app,
        ),
    )

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app)

    await ops_test.model.wait_for_idle(apps=[app_name, rules_app], status="active", timeout=1000)
    global rules_after_relation
    rules_after_relation = await loki_rules(ops_test, app_name)
    assert len(rules_after_relation) == 1


@pytest.mark.abort_on_fail
async def test_second_relation_second_alert_rule(ops_test, loki_tester_charm):
    await asyncio.gather(
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=rules_app2,
        ),
    )

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app2)

    await ops_test.model.wait_for_idle(apps=[app_name, rules_app2], status="active", timeout=1000)

    rules_after_relation2 = await loki_rules(ops_test, app_name)
    assert len(rules_after_relation2) == 2


@pytest.mark.abort_on_fail
async def test_remove_app_one_alert_rules_is_retained(ops_test):
    await ops_test.model.applications[rules_app2].remove()
    try:
        await ops_test.model.block_until(
            lambda: rules_app2 not in ops_test.model.applications, timeout=300
        )
    except asyncio.exceptions.TimeoutError:
        logger.warning(
            "Failed to remove applications: %s",
            ", ".join([app for app in ops_test.model.applications if app in [rules_app2]]),
        )
        hung_apps = [
            app_name
            for app_name, app in ops_test.model.applications.items()
            if len(app.units) == 0 and app.status == "active"
        ]
        if hung_apps:
            for app in hung_apps:
                logger.warning("%s stuck removing. Forcing...", app)
                cmd = [
                    "juju",
                    "remove-application",
                    "--destroy-storage",
                    "--force",
                    "--no-wait",
                    app,
                ]
                logger.info("Forcibly removing {}".format(app))
                await ops_test.run(*cmd)
        else:
            raise
    global rules_after_relation
    rules_after_delete_relation2 = await loki_rules(ops_test, app_name)
    assert rules_after_delete_relation2 == rules_after_relation


@pytest.mark.abort_on_fail
async def test_wrong_alert_rule(ops_test, faulty_loki_tester_charm):
    await ops_test.model.deploy(faulty_loki_tester_charm, application_name=rules_app3)

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app3)
    await ops_test.model.wait_for_idle(apps=[app_name], status="blocked", timeout=1000)
