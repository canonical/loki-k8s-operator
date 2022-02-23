#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from subprocess import Popen, PIPE
from requests import get
import pytest
from helpers import all_combinations, oci_image, get_logpy_path
from charm import LOGFILE
from tests.integration.loki_tester.src.log import (
    SYSLOG_LOG_MSG, LOKI_LOG_MSG, FILE_LOG_MSG)


tester_resources = {
    "loki-tester-image": oci_image(
        "./tests/integration/loki-tester/metadata.yaml", "loki-tester-image"
    )
}


@pytest.mark.abort_on_fail
async def test_build_and_deploy_loki_tester(ops_test, loki_tester_charm):
    """Test that the Loki tester charm can be built and deployed successfully.
    """
    app_name = "loki-tester"

    await ops_test.model.deploy(
        loki_tester_charm, resources=tester_resources, application_name=app_name
    )
    await ops_test.model.wait_for_idle(apps=[app_name], status="active")
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[app_name].units) > 0)

    assert ops_test.model.applications[app_name].units[0].workload_status == "active"

    await ops_test.model.applications[app_name].remove()
    await ops_test.model.block_until(lambda: app_name not in ops_test.model.applications)
    await ops_test.model.reset()


# to run this test against a locally available LOKI node:
# LOKI_ADDRESS="10.1.94.35:3100" pytest ./tests/integration/test_loki_tester.py::test_log_script
@pytest.mark.parametrize(
    'modes',
    all_combinations(
        ('syslog', 'loki', 'file')
    )
)
def test_log_script(modes):
    loki_address = None
    if 'loki' in modes:
        loki_address = os.environ.get('LOKI_ADDRESS')
        if not loki_address:
            pytest.xfail('set envvar LOKI_ADDRESS to a reachable Loki '
                         'node address for the `loki`-mode test to work')

    args = ["python3", get_logpy_path(), modes]
    if loki_address:
        args.append(loki_address)

    proc = Popen(args, stdout=PIPE, stderr=PIPE)

    if 'syslog' in modes:
        with open('/var/log/syslog', 'r') as f:
            logs = f.read()
            assert SYSLOG_LOG_MSG in logs

    if 'loki' in modes:
        resp = get(f"http://{loki_address}/loki/api/v1/label/test/values")
        result = resp.json()
        print(proc.stdout.read())
        print(proc.stderr.read())
        print(result)
        assert result['status'] == 'success'
        assert LOKI_LOG_MSG in result['data']

    if 'file' in modes:
        with open(LOGFILE, 'r') as f:
            assert FILE_LOG_MSG in f.read()
