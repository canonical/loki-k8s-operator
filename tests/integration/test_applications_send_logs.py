#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import time

import jubilant
from helpers import is_loki_up, loki_api_query, oci_image

logger = logging.getLogger(__name__)

tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-proxy-tester/charmcraft.yaml", "workload-image"
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


def test_loki_api_client_logs(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    loki_tester_charm,
    log_proxy_tester_charm,
    log_proxy_tester_resources,
):
    """Test basic functionality of Loki push API relation interface."""
    juju.deploy(loki_charm, loki_app_name, resources=loki_resources, trust=True)
    juju.deploy(loki_tester_charm, "loki-tester")
    juju.deploy(
        log_proxy_tester_charm,
        "log-proxy-tester-file",
        resources=log_proxy_tester_resources,
    )
    juju.deploy(
        log_proxy_tester_charm,
        "log-proxy-tester-syslog",
        resources=log_proxy_tester_resources,
        config={"syslog": "true", "file_forwarding": "false"},
    )

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    for tester in tester_app_names:
        juju.integrate(loki_app_name, tester)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    for query in tester_apps.values():
        logs = loki_api_query(juju, loki_app_name, query, unit_num=0)
        assert len(logs) > 0 and len(logs[0]["values"]) > 0


def test_scale_up_also_gets_logs(juju: jubilant.Juju):
    juju.cli("scale-application", loki_app_name, "3")
    juju.wait(
        lambda status: (
            jubilant.all_active(status)
            and jubilant.all_agents_idle(status)
            and len(status.apps[loki_app_name].units) == 3
        ),
        timeout=10 * 60,
    )
    assert is_loki_up(juju, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on just to ensure we have logs
    juju.run("loki-tester/0", "log-error", {"message": "Error logged!"})
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )
    # Give Loki some extra time to propagate logs
    time.sleep(60)

    assert is_loki_up(juju, loki_app_name, num_units=3)

    for query in tester_apps.values():
        logs_per_unit = [
            loki_api_query(juju, loki_app_name, query, unit_num=i) for i in range(3)
        ]
        assert all(len(logs) > 0 and len(logs[0]["values"]) > 0 for logs in logs_per_unit)


def test_logs_persist_after_upgrade(juju: jubilant.Juju, loki_charm, loki_resources):
    counts_before_upgrade = {}
    for tester, query in tester_apps.items():
        count_query = f"count_over_time({query}[30m])"
        counts_before_upgrade[tester] = [
            loki_api_query(juju, loki_app_name, count_query, unit_num=i) for i in range(3)
        ]

    # Refresh from path
    juju.cli("refresh", loki_app_name, f"--path={loki_charm}")
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )
    # Give Loki some extra time after upgrade
    time.sleep(60)
    assert is_loki_up(juju, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on just to ensure we have logs
    result = juju.run("loki-tester/0", "log-error", {"message": "Error logged!"})
    assert result.success
    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=15 * 60,
    )
    time.sleep(15)

    counts_after_upgrade = {}
    for tester, query in tester_apps.items():
        count_query = f"count_over_time({query}[30m])"
        counts_after_upgrade[tester] = [
            loki_api_query(juju, loki_app_name, count_query, unit_num=i) for i in range(3)
        ]

    values_before_upgrade = return_last_value_from_loki_count(counts_before_upgrade)
    values_after_upgrade = return_last_value_from_loki_count(counts_after_upgrade)

    for client, values in values_after_upgrade.items():
        # If any of the log counts are higher, we are continuing. Don't depend on
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
