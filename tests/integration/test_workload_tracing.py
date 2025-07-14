#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import get_application_ip, get_traces_patiently, is_loki_up
from minio import Minio
from pytest_operator.plugin import OpsTest

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
async def test_workload_tracing_is_present(ops_test: OpsTest, loki_charm):
    assert ops_test.model
    juju = jubilant.Juju(model=ops_test.model_name)
    minio_user = "accesskey"
    minio_pass = "secretkey"
    minio_bucket = "tempo"

    # GIVEN a model with tempo charms
    juju.deploy(charm="tempo-coordinator-k8s", app="tempo", channel="2/edge", trust=True)
    juju.deploy(charm="tempo-worker-k8s", app="tempo-worker", channel="2/edge", trust=True)
    # Set up minio and s3-integrator
    juju.deploy(
        charm="minio",
        app="minio-tempo",
        trust=True,
        config={"access-key": minio_user, "secret-key": minio_pass},
    )
    juju.deploy(charm="s3-integrator", app="s3-tempo", channel="edge")
    juju.wait(lambda status: jubilant.all_active(status, "minio-tempo"), delay=5)
    minio_address = juju.status().apps["minio-tempo"].units["minio-tempo/0"].address
    minio_client: Minio = Minio(
        f"{minio_address}:9000",
        access_key=minio_user,
        secret_key=minio_pass,
        secure=False,
    )
    if not minio_client.bucket_exists(minio_bucket):
        minio_client.make_bucket(minio_bucket)
    juju.config("s3-tempo", {"endpoint": f"{minio_address}:9000", "bucket": minio_bucket})
    juju.run(
        unit="s3-tempo/0",
        action="sync-s3-credentials",
        params={"access-key": minio_user, "secret-key": minio_pass},
    )
    juju.integrate("tempo:s3", "s3-tempo")
    juju.integrate("tempo:tempo-cluster", "tempo-worker")

    logger.info("deploying local charm")
    juju.deploy(loki_charm, app="loki", resources=loki_resources, trust=True)
    juju.wait(jubilant.all_active)

    # we relate _only_ workload tracing not to confuse with charm traces
    juju.integrate("loki:workload-tracing", "tempo:tracing")
    # but we also need anything to come in to loki so that loki generates traces
    juju.integrate("loki:logging", "tempo:logging")
    juju.wait(jubilant.all_active)
    assert await is_loki_up(ops_test, app_name, num_units=1)

    # Verify workload traces are ingested into Tempo
    assert await get_traces_patiently(
        await get_application_ip(ops_test, TEMPO_APP_NAME),
        service_name=f"{app_name}",
        tls=False,
    )
