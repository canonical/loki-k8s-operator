#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from helpers import (
    get_application_ip,
    get_traces_patiently,
    get_unit_address,
    is_loki_up,
)
from minio import Minio

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
    # Deploy a Tempo cluster
    minio_user = "accesskey"
    minio_pass = "secretkey"
    minio_bucket = "tempo"

    await ops_test.model.deploy(
        "tempo-worker-k8s", application_name="tempo-worker", channel=cos_channel, trust=True
    )
    await ops_test.model.deploy(
        "tempo-coordinator-k8s",
        application_name=TEMPO_APP_NAME,
        channel=cos_channel,
        trust=True,
    )
    # Set up minio and s3-integrator
    await ops_test.model.deploy("minio",application_name="minio-tempo", trust=True, config={"access-key": minio_user, "secret-key": minio_pass})
    await ops_test.model.deploy("s3-integrator", application_name="s3-tempo", channel="edge")

    await ops_test.model.wait_for_idle(
            apps=["minio-tempo"],
            status="active",
            timeout=2000,
            idle_period=30,
        )
    minio_addr = await get_unit_address(ops_test, "minio-tempo", 0)
    mc_client = Minio(
        f"{minio_addr}:9000",
        access_key=minio_user,
        secret_key=minio_pass,
        secure=False,
    )
    # create tempo bucket
    found = mc_client.bucket_exists(minio_bucket)
    if not found:
        mc_client.make_bucket(minio_bucket)

    s3_integrator_app = ops_test.model.applications["s3-tempo"]  # type: ignore
    s3_integrator_leader = s3_integrator_app.units[0]

    await s3_integrator_app.set_config(
        {
            "endpoint": f"{minio_addr}:9000",
            "bucket": minio_bucket,
        }
    )

    action = await s3_integrator_leader.run_action("sync-s3-credentials", {"access-key": minio_user, "secret-key": minio_pass})
    await action.wait()

    await ops_test.model.integrate(f"{TEMPO_APP_NAME}:s3", "s3-tempo")
    await ops_test.model.integrate(f"{TEMPO_APP_NAME}:tempo-cluster", "tempo-worker")

    logger.info("deploying local charm")
    await ops_test.model.deploy(
        loki_charm, resources=loki_resources, application_name=app_name, trust=True
    )
    await ops_test.model.wait_for_idle(
        apps=[app_name], status="active", timeout=300, idle_period=30,
    )

    # we relate _only_ workload tracing not to confuse with charm traces
    await ops_test.model.add_relation(
        f"{app_name}:workload-tracing", f"{TEMPO_APP_NAME}:tracing"
    )
    # but we also need anything to come in to loki so that loki generates traces
    await ops_test.model.add_relation(
        f"{TEMPO_APP_NAME}:logging", f"{app_name}:logging"
    )
    await ops_test.model.wait_for_idle(apps=[app_name, TEMPO_APP_NAME, "tempo-worker"], status="active", idle_period=30)
    assert await is_loki_up(ops_test, app_name, num_units=1)

    # Verify workload traces are ingested into Tempo
    assert await get_traces_patiently(
        await get_application_ip(ops_test, TEMPO_APP_NAME),
        service_name=f"{app_name}",
        tls=False,
    )
