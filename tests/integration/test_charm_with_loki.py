#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Sequence

import pytest
import requests
from charms.loki_k8s.v0.loki_push_api import (
    BINARY_FILE_NAME,
    WORKLOAD_BINARY_DIR,
    WORKLOAD_CONFIG_DIR,
    WORKLOAD_CONFIG_FILE_NAME,
    WORKLOAD_CONFIG_PATH,
)
from helpers import all_combinations
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_exponential

# copied over from log.py to avoid circular imports
from tests.integration.helpers import (
    check_file_exists_in_loki_tester_unit,
    get_loki_address,
    loki_api_query_range,
    populate_template,
    run_in_loki_tester,
)

TEST_JOB_NAME = "test-job"
# for some reason the syslog log message gets decoded with
# this \ufeff thing prepended
SYSLOG_LOG_MSG = "\ufeffLOG SYSLOG"
LOKI_LOG_MSG = "LOG LOKI"
FILE_LOG_MSG = "LOG FILE"

LOKI_READY_TIMEOUT = 60  # it typically takes around 15s on my machine
LOKI_READY_RETRY_SLEEP = 1

JUJU_MODEL_UUID_KEY = "juju_model_uuid"
PROMTAIL_JOB_TEMPLATE = "juju_{model_name}_{uuid}_loki-tester_loki-tester_loki-tester"
STREAM_TEMPLATE = {
    "juju_application": "loki-tester",
    "juju_charm": "loki-tester",
    "juju_model": "{model_name}",
    JUJU_MODEL_UUID_KEY: "{uuid}",
    "juju_unit": "loki-tester/0",
}

# We need to add dependency to loki_tester_deployment to ensure that if setup
# aborts then this test is skipped too. Else it may fail with an odd message.
async def test_logpy_is_in_workload_container(ops_test: OpsTest, loki_tester_deployment):  # noqa
    """Verify that log.py is in the container."""
    # this could be done in a smarter way I guess
    assert await check_file_exists_in_loki_tester_unit(ops_test, "/", "log.py")


# We need to add dependency to loki_tester_deployment to ensure that if setup
# aborts then this test is skipped too. Else it may fail with an odd message.
async def test_promtail_files_are_in_workload_container(
    ops_test: OpsTest, loki_tester_deployment
):  # noqa
    """Verify that the promload binary and the config are where they should."""
    assert await check_file_exists_in_loki_tester_unit(
        ops_test, WORKLOAD_BINARY_DIR + "/", BINARY_FILE_NAME
    )
    assert await check_file_exists_in_loki_tester_unit(
        ops_test, WORKLOAD_CONFIG_DIR + "/", WORKLOAD_CONFIG_FILE_NAME
    )


# We need to add dependency to loki_tester_deployment to ensure that if setup
# aborts then this test is skipped too. Else it may fail with an odd message.
async def test_promtail_is_running_in_workload_container(
    ops_test: OpsTest, loki_tester_deployment  # noqa
):
    """Verify that the promtail process is running."""
    await run_in_loki_tester(ops_test, "apt update -y && apt install procps -y")
    return_code, stdout, stderr = await run_in_loki_tester(ops_test, "ps -aux | grep promtail")
    cmd = f"{BINARY_FILE_NAME} -config.file={WORKLOAD_CONFIG_PATH}"
    assert cmd in stdout


# We need to add dependency to loki_tester_deployment to ensure that if setup
# aborts then this test is skipped too. Else it may fail with an odd message.
async def test_log_proxy_relation_data(ops_test: OpsTest, loki_tester_deployment):  # noqa
    """Verify that loki:log-proxy has set some 'endpoints' application data."""
    return_code, stdout, stderr = await ops_test.juju(
        "show-unit", "loki-tester/0", "--format=json"
    )

    data = json.loads(stdout)
    lp_relation_info = data["loki-tester/0"]["relation-info"][0]

    endpoints = lp_relation_info["application-data"].get("endpoints")
    assert endpoints
    assert json.loads(endpoints)[0].get("url")


@pytest.mark.abort_on_fail
@retry(wait=wait_exponential(multiplier=1, min=10, max=60), stop=stop_after_attempt(7))
async def test_loki_ready(ops_test: OpsTest, loki_tester_deployment):
    loki_app_name, loki_tester_app_name = loki_tester_deployment
    loki_address = await get_loki_address(ops_test, loki_app_name)
    resp = requests.get(f"http://{loki_address}:3100/ready")

    assert resp.status_code == 200
    assert resp.text.strip() == "ready"


@pytest.mark.parametrize("modes", all_combinations(("loki", "file", "syslog")))
@pytest.mark.abort_on_fail
async def test_loki_scraping_with_promtail(
    modes: Sequence[str], ops_test: OpsTest, loki_tester_deployment
):
    """Test the core loki functionality + promtail on several log output cases.

    Will run on all combinations of loki/file/syslog routes.
    """
    loki_app_name, loki_tester_app_name = loki_tester_deployment

    # we block until loki is ready before proceeding, else the tester
    # app will fire into the void and give errors
    loki_address = await get_loki_address(ops_test, loki_app_name)

    # at this point the workload should run and fire the logs to
    # the configured targets
    await ops_test.juju("config", loki_tester_app_name, f"log-to={','.join(modes)}")
    await ops_test.model.wait_for_idle(apps=[loki_tester_app_name], status="active")

    # by now all logs should be in loki. if this races, we might want to
    # introduce a little sleep here, or await loki to show something for a
    # little while.

    # get all existing job labels
    jobs = (
        requests.get(f"http://{loki_address}:3100/loki/api/v1/label/job/values").json().get("data")
    )
    assert jobs, "no jobs present: nothing was logged yet."

    if "loki" in modes:
        assert TEST_JOB_NAME in jobs
        assert await _check_job_logged(TEST_JOB_NAME, LOKI_LOG_MSG, loki_address)
        stream = {"job": TEST_JOB_NAME}
        assert await _check_all_streams_equal(TEST_JOB_NAME, loki_address, stream)

    if "file" in modes:
        job = next(filter(lambda x: x.endswith("loki-tester"), jobs))
        assert await _check_job_logged(job, FILE_LOG_MSG, loki_address)

        extra_stream = {"filename": "/loki_tester_msgs.txt"}
        assert await _check_stream_matches_template(job, loki_address, extra_stream=extra_stream)

    if "syslog" in modes:
        job = next(filter(lambda x: x.endswith("loki-tester_syslog"), jobs))
        assert await _check_job_logged(job, SYSLOG_LOG_MSG, loki_address)
        assert await _check_stream_matches_template(job, loki_address)


async def _check_job_logged(job_name: str, msg: str, loki_address: str):
    results = loki_api_query_range(job_name, loki_address)
    try:
        return results and results[0]["values"][0][1] == msg
    except KeyError:
        return False


async def _check_stream_matches_template(job_name, loki_address, extra_stream=None):
    results = loki_api_query_range(job_name, loki_address)
    # we fill in the stream template with model uuid and model name, which vary.
    # any result will do for this, as they should be all the same.
    expected_stream = populate_template(STREAM_TEMPLATE, results[0])

    if extra_stream:
        expected_stream.update(extra_stream)
    return _check_all_equal(results, expected_stream)


async def _check_all_streams_equal(job_name, loki_address, stream):
    results = loki_api_query_range(job_name, loki_address)
    return _check_all_equal(results, stream)


def _check_all_equal(values, expected_stream):
    # returns True iff each value's ['stream'] is equal to expected_stream
    for value in values:
        if value["stream"] != expected_stream:
            return False
    return True
