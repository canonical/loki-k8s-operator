#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import pytest
from helpers import oci_image

this_file = Path(__file__).parent.resolve()
metadata_file = (this_file / "loki_tester" / "metadata.yaml").absolute()
if not metadata_file.exists():
    raise RuntimeError(f"path to metadata.yaml incorrect: {metadata_file}")
tester_resources = {"loki-tester-image": oci_image(metadata_file, "loki-tester-image")}


@pytest.mark.abort_on_fail
async def test_build_and_deploy_loki_tester(ops_test, loki_tester_charm):
    """Test that the Loki tester charm can be built and deployed."""
    app_name = "loki-tester"

    await ops_test.model.deploy(
        loki_tester_charm, resources=tester_resources, application_name=app_name
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active")
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[app_name].units) > 0)

    unit = ops_test.model.applications[app_name].units
    assert unit[0].workload_status == "active"

    await ops_test.model.applications[app_name].remove()
    await ops_test.model.block_until(lambda: app_name not in ops_test.model.applications)
    await ops_test.model.reset()
