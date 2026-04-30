#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import (
    all_active_idle,
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


def test_setup_env(juju: jubilant.Juju):
    juju.model_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.skip("tracing-relation-joined fails - https://github.com/canonical/cos-coordinated-workers/issues/19")
def test_workload_tracing_is_present(juju: jubilant.Juju, loki_charm, cos_channel):
    # Deploy a Tempo cluster
    minio_user = "accesskey"
    minio_pass = "secretkey"
    minio_bucket = "tempo"

    juju.deploy("tempo-worker-k8s", "tempo-worker", channel=cos_channel, trust=True)
    juju.deploy("tempo-coordinator-k8s", TEMPO_APP_NAME, channel=cos_channel, trust=True)
    # Set up minio and s3-integrator
    juju.deploy(
        "minio",
        "minio-tempo",
        channel="edge",
        trust=True,
        config={"access-key": minio_user, "secret-key": minio_pass},
    )
    juju.deploy("s3-integrator", "s3-tempo", channel="edge")

    juju.wait(lambda s: all_active_idle(s, "minio-tempo"), timeout=2000)
    minio_addr = get_unit_address(juju, "minio-tempo", 0)
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

    juju.config("s3-tempo", {"endpoint": f"{minio_addr}:9000", "bucket": minio_bucket})
    juju.run(
        "s3-tempo/0",
        "sync-s3-credentials",
        params={"access-key": minio_user, "secret-key": minio_pass},
    )

    juju.integrate(f"{TEMPO_APP_NAME}:s3", "s3-tempo")
    juju.integrate(f"{TEMPO_APP_NAME}:tempo-cluster", "tempo-worker")

    logger.info("deploying local charm")
    juju.deploy(loki_charm, app_name, resources=loki_resources, trust=True)
    juju.wait(lambda s: all_active_idle(s, app_name), timeout=300)

    # we relate _only_ workload tracing not to confuse with charm traces
    juju.integrate(f"{app_name}:workload-tracing", f"{TEMPO_APP_NAME}:tracing")
    # but we also need anything to come in to loki so that loki generates traces
    juju.integrate(f"{TEMPO_APP_NAME}:logging", f"{app_name}:logging")
    juju.wait(
        lambda s: all_active_idle(s, app_name, TEMPO_APP_NAME, "tempo-worker"),
        timeout=1000,
    )
    assert is_loki_up(juju, app_name, num_units=1)

    # Verify workload traces are ingested into Tempo
    assert get_traces_patiently(
        get_application_ip(juju, TEMPO_APP_NAME),
        service_name=app_name,
        tls=False,
    )
