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
from collections import namedtuple
from pathlib import Path

import pytest
import yaml
from helpers import ModelConfigChange, is_loki_up
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}

RelatedApp = namedtuple("RelatedApp", ["name", "src", "relname", "config"])
related_apps = [
    RelatedApp("alertmanager", "ch:alertmanager-k8s", "alertmanager", {}),
    RelatedApp("cassandra", "ch:cassandra-k8s", "logging", {"heap_size": "1g"}),
]


# class RelatedApp2:
#     def __init__(self, name: str, src: str, relname: str, config: dict):
#         self.name = name
#         self.src = src
#         self.relname = relname
#         self.config = config
#
#     async def deploy(self, ops_test: OpsTest):
#         await ops_test.model.deploy(
#             self.src, application_name=self.name, channel="edge", config=self.config
#         )
#
#
# related_apps2 = [
#     RelatedApp2("alertmanager", "ch:alertmanager-k8s", "alertmanager", {}),
#     RelatedApp2("cassandra", "ch:cassandra-k8s", "loki_push_api", {}),
# ]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, loki_charm):
    """Build the charm-under-test and deploy it together with related charms."""
    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm, resources=resources, application_name=app_name, num_units=2
        ),
        *[
            ops_test.model.deploy(
                app.src, application_name=app.name, channel="edge", config=app.config
            )
            for app in related_apps
        ],
        # *[app.deploy(ops_test) for app in related_apps2],
    )

    await asyncio.gather(
        *[ops_test.model.add_relation(app_name, app.name) for app in related_apps],
    )

    async with ModelConfigChange(ops_test, {"update-status-hook-interval": "60s"}):
        await ops_test.model.wait_for_idle(status="active", timeout=1000)

    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_remove_relation(ops_test: OpsTest):
    await asyncio.gather(
        *[
            ops_test.model.applications[app_name].remove_relation(app.relname, app.name)
            for app in related_apps
        ],
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_rerelate(ops_test: OpsTest):
    await asyncio.gather(
        *[ops_test.model.add_relation(app_name, app.name) for app in related_apps],
    )
    await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_remove_related_app(ops_test: OpsTest):
    await asyncio.gather(
        *[ops_test.model.applications[app.name].remove() for app in related_apps],
        # Block until it is really gone. Added after an itest failed when tried to redeploy:
        # juju.errors.JujuError: ['cannot add application "...": application already exists']
        *[
            ops_test.model.block_until(lambda: app.name not in ops_test.model.applications)
            for app in related_apps
        ],
    )

    await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)


@pytest.mark.abort_on_fail
async def test_rerelate_app(ops_test: OpsTest):
    await asyncio.gather(
        *[
            ops_test.model.deploy(
                app.src, application_name=app.name, channel="edge", config=app.config
            )
            for app in related_apps
        ],
    )
    await asyncio.gather(
        *[ops_test.model.add_relation(app_name, app.name) for app in related_apps],
    )

    async with ModelConfigChange(ops_test, {"update-status-hook-interval": "60s"}):
        await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert await is_loki_up(ops_test, app_name)
