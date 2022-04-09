#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This test module tests loki response to related apps being removed and re-related.

1. Deploy the charm under test and a related app, relate them and wait for them to become idle.
2. Remove the relation.
3. Re-add the relation.
4. Remove the related application.
5. Redeploy the related application and add the relation back again.
"""

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up, oci_image
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}
tester_resources = {
    "loki-tester-image": oci_image(
        "./tests/integration/loki-tester/metadata.yaml", "loki-tester-image"
    )
}


class RelatedApp:
    def __init__(self, name: str, src: str, relname: str, config: dict):
        self.name = name
        self.src = src
        self.relname = relname
        self.config = config

    async def deploy(self, ops_test: OpsTest):
        await ops_test.model.deploy(
            self.src, application_name=self.name, channel="edge", config=self.config
        )


async def test_setup_env(ops_test: OpsTest):
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, loki_charm, loki_tester_charm):
    """Build the charm-under-test and deploy it together with related charms."""
    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm, resources=resources, application_name=app_name, num_units=2
        ),
        ops_test.model.deploy(
            loki_tester_charm,
            resources=tester_resources,
            application_name="loki-tester",
        ),
        ops_test.model.deploy(
            "ch:alertmanager-k8s",
            application_name="alertmanager",
            channel="edge",
        ),
    )

    await asyncio.gather(
        ops_test.model.add_relation(app_name, "loki-tester"),
        ops_test.model.add_relation(app_name, "alertmanager"),
    )
    await ops_test.model.wait_for_idle(status="active", timeout=600)

    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_remove_relation(ops_test: OpsTest):
    await asyncio.gather(
        ops_test.model.applications[app_name].remove_relation("logging", "loki-tester"),
        ops_test.model.applications[app_name].remove_relation("alertmanager", "alertmanager"),
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_rerelate(ops_test: OpsTest):
    await asyncio.gather(
        ops_test.model.add_relation(app_name, "loki-tester"),
        ops_test.model.add_relation(app_name, "alertmanager"),
    )
    await ops_test.model.wait_for_idle(status="active", timeout=600)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_remove_related_app(ops_test: OpsTest):
    await asyncio.gather(
        ops_test.model.applications["loki-tester"].remove(),
        ops_test.model.applications["alertmanager"].remove(),
    )
    logger.debug("Applications removed. Blocking for 60 seconds then force removing...")
    # Block until it is really gone. Added after an itest failed when tried to redeploy:
    # juju.errors.JujuError: ['cannot add application "...": application already exists']
    try:
        await ops_test.model.block_until(
            lambda: "loki-tester" not in ops_test.model.applications,
            lambda: "alertmanager" not in ops_test.model.applications,
            timeout=60,
        )
    except asyncio.exceptions.TimeoutError:
        logger.warning("Timeout reached while blocking!")

    for app in filter(lambda x: x in ops_test.model.applications, ["loki-tester", "alertmanager"]):
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

    await ops_test.model.wait_for_idle(apps=[app_name], timeout=600)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_rerelate_app(ops_test: OpsTest, loki_tester_charm):
    await asyncio.gather(
        ops_test.model.deploy(
            loki_tester_charm,
            resources=tester_resources,
            application_name="loki-tester",
        ),
        ops_test.model.deploy(
            "ch:alertmanager-k8s",
            application_name="alertmanager",
            channel="edge",
        ),
    )

    await asyncio.gather(
        ops_test.model.add_relation(app_name, "loki-tester"),
        ops_test.model.add_relation(app_name, "alertmanager"),
    )
    await ops_test.model.wait_for_idle(status="active", timeout=600)

    assert await is_loki_up(ops_test, app_name)
