#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from helpers import is_loki_up, loki_api_query, oci_image

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-proxy-tester/metadata.yaml", "workload-image"
    )
}


# WARNING: the Loki query API is very finicky about quoting. It MUST be surrounded
# with single quotes and have double quotes inside, or the return code will be 400.
#
# Proceed with care
tester_apps = {
    "loki-tester": '{juju_application="loki-tester",level="debug"}',
    "log-proxy-tester-file": '{juju_application="log-proxy-tester-file",filename=~".+"}',
    "log-proxy-tester-syslog": '{juju_application="log-proxy-tester-syslog",job=~".+syslog"}',
}


loki_app_name = "loki"
tester_app_names = list(tester_apps.keys())
app_names = [loki_app_name] + tester_app_names


@pytest.mark.abort_on_fail
async def test_loki_api_client_logs(
    ops_test, loki_charm, loki_tester_charm, log_proxy_tester_charm
):
    """Test basic functionality of Loki push API relation interface."""
    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
            trust=True,
        ),
        ops_test.model.deploy(loki_tester_charm, application_name="loki-tester"),
        ops_test.model.deploy(
            log_proxy_tester_charm,
            resources=tester_resources,
            application_name="log-proxy-tester-file",
        ),
        ops_test.model.deploy(
            log_proxy_tester_charm,
            resources=tester_resources,
            application_name="log-proxy-tester-syslog",
            config={"syslog": "true", "file_forwarding": "false"},
        ),
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await asyncio.gather(
        *[ops_test.model.add_relation(loki_app_name, t) for t in tester_app_names]
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    for query in tester_apps.values():
        logs_per_unit = await asyncio.gather(
            loki_api_query(ops_test, loki_app_name, query, unit_num=0),
        )
        assert all(len(logs[0]["values"]) > 0 for logs in logs_per_unit)


@pytest.mark.abort_on_fail
async def test_scale_up_also_gets_logs(ops_test):
    await ops_test.model.applications[loki_app_name].scale(scale=3)
    await ops_test.model.wait_for_idle(
        apps=[loki_app_name], status="active", timeout=600, wait_for_exact_units=3
    )
    assert await is_loki_up(ops_test, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on just to ensure we have logs
    await ops_test.model.applications["loki-tester"].units[0].run_action(
        "log-error", message="Error logged!"
    )
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=60
    )

    assert await is_loki_up(ops_test, loki_app_name, num_units=3)

    for query in tester_apps.values():
        logs_per_unit = await asyncio.gather(
            loki_api_query(ops_test, loki_app_name, query, unit_num=0),
            loki_api_query(ops_test, loki_app_name, query, unit_num=1),
            loki_api_query(ops_test, loki_app_name, query, unit_num=2),
        )
        assert all(len(logs[0]["values"]) > 0 for logs in logs_per_unit)


@pytest.mark.abort_on_fail
async def test_logs_persist_after_upgrade(ops_test, loki_charm):
    counts_before_upgrade = {}
    for tester, query in tester_apps.items():
        query = f"count_over_time({query}[30m])"
        counts_before_upgrade[tester] = await asyncio.gather(
            loki_api_query(ops_test, loki_app_name, query, unit_num=0),
            loki_api_query(ops_test, loki_app_name, query, unit_num=1),
            loki_api_query(ops_test, loki_app_name, query, unit_num=2),
        )

    # Refresh from path
    await ops_test.model.applications[loki_app_name].refresh(path=loki_charm, resources=resources)
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=60
    )
    assert await is_loki_up(ops_test, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on just to ensure we have logs
    action = (
        await ops_test.model.applications["loki-tester"]
        .units[0]
        .run_action("log-error", message="Error logged!")
    )
    (await action.wait()).results["message"]
    await ops_test.model.wait_for_idle(
        apps=app_names, status="active", timeout=1000, idle_period=15
    )

    counts_after_upgrade = {}
    for tester, query in tester_apps.items():
        query = f"count_over_time({query}[30m])"
        counts_after_upgrade[tester] = await asyncio.gather(
            loki_api_query(ops_test, loki_app_name, query, unit_num=0),
            loki_api_query(ops_test, loki_app_name, query, unit_num=1),
            loki_api_query(ops_test, loki_app_name, query, unit_num=2),
        )

    values_before_upgrade = return_last_value_from_loki_count(counts_before_upgrade)
    values_after_upgrade = return_last_value_from_loki_count(counts_after_upgrade)

    for client, values in values_after_upgrade.items():
        # If any of the log counts are higher, we are continuiting. Don't depend on
        # timing the log entries
        assert any(
            values_after_upgrade[client][idx] > values_before_upgrade[client][idx]
            for idx in range(len(values))
        )


def return_last_value_from_loki_count(item: dict) -> dict:
    # The structure here will be:
    # { <app_name> : [
    #   [
    #       { "metric": <labels>,
    #            "values": [
    #                [ <timestamp>, <count> ],
    #            ]
    #        }
    #    ] * [<num_loki_servers>]
    # So we are comparing: counts[<app_name>][<foreach loki in lokis>][values][-1][1]
    #
    # There's not a pretty way to pull it out, really
    ret = {}  # type: ignore
    for client, result in item.items():
        ret[client] = []

        for res in result:
            ret[client].append(int(res[0]["values"][-1][1]))

        # Sort they keys since the order of lokis is not deterministic when
        # we gather results
        ret[client].sort()

    return ret
