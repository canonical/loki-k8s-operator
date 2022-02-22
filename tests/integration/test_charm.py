#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
from pathlib import Path
from subprocess import Popen, PIPE

import pytest
import yaml
from tests.integration.loki_tester.src.log import (
    SYSLOG_LOG_MSG, LOKI_LOG_MSG, FILE_LOG_MSG)
from pytest_operator.plugin import OpsTest
from helpers import IPAddressWorkaround, all_combinations, is_loki_up

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]
             ["loki-image"]["upstream-source"]}


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test, loki_charm):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    await ops_test.model.deploy(loki_charm, resources=resources, application_name=app_name)

    async with IPAddressWorkaround(ops_test):
        await ops_test.model.wait_for_idle(apps=[app_name], status="active", timeout=1000)
        assert ops_test.model.applications[app_name].units[0].workload_status == "active"

    assert await is_loki_up(ops_test, app_name)


@pytest.mark.parametrize(
    'modes',
    all_combinations(
        ('stdout', 'stderr', 'syslog', 'loki', 'file')
    )
)
@pytest.mark.abort_on_fail
async def test_prometheus_scrape_relation_with_prometheus_tester(
    modes: str, ops_test: OpsTest, loki_tester_deployment
):
    """Test the core loki functionality + promtail on several log output 
    scenarios.
    """
    loki_app_name, loki_tester_app_name = loki_tester_deployment
    # we configure the loki tester app
    ops_test.run(f'config {loki_tester_app_name} {modes}')
    ops_test.run(f'expose {loki_app_name}/0')
    
    # obtain the loki cluster IP to make direct api calls
    cmd = Popen(f"juju status {loki_tester_app_name} --format=json".split(" "), stdout=PIPE)
    jsn = json.loads(cmd.stdout.read().decode('utf-8'))
    ip = jsn["applications"][f"{loki_tester_app_name}"]["units"]\
        [f"{loki_tester_app_name}/0"]["address"]
        
    for mode in modes.split(','):
        assert_logs_in_loki(mode, loki_app_name, ops_test, ip)


async def assert_logs_in_loki(mode: str, loki_app_name: str, ops_test: OpsTest, 
                              ip: str):
    def get(endpoint):
        import requests
        resp = requests.get(f"http://{ip}:3100/{endpoint}")
        return resp.content.decode('utf-8')
    
    if mode == 'syslog':
        assert SYSLOG_LOG_MSG in get() 
    elif mode == 'loki':
        assert LOKI_LOG_MSG in get() 
    else: # `file`
        assert FILE_LOG_MSG in get()
    