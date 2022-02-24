#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import IPAddressWorkaround, is_loki_up, loki_rules

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}
rules_app = "cos-config"


@pytest.mark.abort_on_fail
async def test_deploy_charms(ops_test):
    """Deploy from charmhub and form relations."""
    logger.debug("deploy charms from charmhub")
    await asyncio.gather(
        ops_test.model.deploy(f"ch:{app_name}", application_name=app_name, channel="edge"),
        ops_test.model.deploy(
            "ch:cos-configuration-k8s",
            application_name=rules_app,
            channel="edge",
            config={
                "git_repo": "https://github.com/canonical/loki-k8s-operator",
                "git_branch": "main",
                "loki_alert_rules_path": "tests/sample_rule_files/free-standing",
            },
        ),
    )

    # force an update, just in case the files showed up on disk after the last hook fired
    action = await ops_test.model.applications[rules_app].units[0].run_action("sync-now")
    await action.wait()

    # form a relation between loki and the app that provides rules
    await ops_test.model.add_relation(app_name, rules_app)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(
            apps=[app_name, rules_app], status="active", timeout=1000
        )

    # verify setup is complete and as expected
    rules = await loki_rules(ops_test, app_name)
    assert rules == {"not": "really"}


async def test_rule_files_are_retained_after_pod_upgraded(ops_test, loki_charm):
    """Deploy from charmhub and then upgrade with the charm-under-test."""
    logger.debug("upgrade deployed charm with local charm %s", loki_charm)
    await ops_test.model.applications[app_name].refresh(path=loki_charm, resources=resources)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)

    assert await is_loki_up(ops_test, app_name)
    assert ops_test.model.applications[app_name].data["alert_rules"] == {"not": "really"}
