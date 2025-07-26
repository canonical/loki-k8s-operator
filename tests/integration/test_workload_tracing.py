#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from helpers import deploy_tempo_cluster, get_application_ip, get_traces_patiently, is_loki_up

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
app_name = "loki"
TEMPO_APP_NAME = "tempo"
loki_resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


async def test_setup_env(ops_test):
    await ops_test.model.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_workload_tracing_is_present(ops_test, loki_charm, cos_channel):
    logger.info("deploying tempo cluster")
    await deploy_tempo_cluster(ops_test, cos_channel)

    logger.info("deploying local charm")
    await ops_test.model.deploy(
        loki_charm, resources=loki_resources, application_name=app_name, trust=True
    )
    await ops_test.model.wait_for_idle(
        apps=[app_name], status="active", timeout=300, idle_period=30,
    )

    # we relate _only_ workload tracing not to confuse with charm traces
    await ops_test.model.add_relation(
        "{}:workload-tracing".format(app_name), "{}:tracing".format(TEMPO_APP_NAME)
    )
    # but we also need anything to come in to loki so that loki generates traces
    await ops_test.model.add_relation(
        "{}:logging".format(TEMPO_APP_NAME), "{}:logging".format(app_name)
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active", idle_period=30)
    assert await is_loki_up(ops_test, app_name, num_units=1)

    # Verify workload traces are ingested into Tempo
    assert await get_traces_patiently(
        await get_application_ip(ops_test, TEMPO_APP_NAME),
        service_name=f"{app_name}",
        tls=False,
    )
