#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
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
TEST_JOB_NAME = "test-job"
# for some reason the syslog log message gets decoded with
# this \ufeff thing prepended
SYSLOG_LOG_MSG = "\ufeffLOG SYSLOG"
LOKI_LOG_MSG = "LOG LOKI"
FILE_LOG_MSG = "LOG FILE"


async def run_in_loki_tester(ops_test: OpsTest, cmd):
    cmd_line = f"juju ssh --container loki-tester loki-tester/0 {cmd}"
    return await ops_test.run(*cmd_line.split(" "))


async def assert_file_exists(ops_test, file_path, file_name):
    retcode, stdout, stderr = await run_in_loki_tester(
        ops_test, f"ls -l {file_path}{file_name}| grep {file_name}"
    )
    assert stdout
    assert not stderr
    assert retcode == 0


async def test_logpy_is_in_workload_container(ops_test: OpsTest, loki_tester_deployment):
    """Verify that log.py is in the container."""
    # this could be done in a smarter way I guess
    await assert_file_exists(ops_test, "/", "log.py")


async def test_promtail_files_are_in_workload_container(ops_test: OpsTest, loki_tester_deployment):
    """Verify that the promload binary and the config are where they should."""
    await assert_file_exists(ops_test, WORKLOAD_BINARY_DIR + "/", BINARY_FILE_NAME)
    await assert_file_exists(ops_test, WORKLOAD_CONFIG_DIR + "/", WORKLOAD_CONFIG_FILE_NAME)


async def test_promtail_is_running_in_workload_container(
    ops_test: OpsTest, loki_tester_deployment
):
    """Verify that the promtail process is running."""
    await run_in_loki_tester(ops_test, "apt update -y && apt install procps -y")
    retcode, stdout, stderr = await run_in_loki_tester(ops_test, "ps -aux | grep promtail")
    cmd = f"{BINARY_FILE_NAME} -config.file={WORKLOAD_CONFIG_PATH}"
    assert cmd in stdout


async def get_loki_address(ops_test, loki_app_name):
    # obtain the loki cluster IP to make direct api calls
    retcode, stdout, stderr = await ops_test.juju("status", "--format=json")
    try:
        jsn = json.loads(stdout)
        return jsn["applications"][loki_app_name]["units"][f"{loki_app_name}/0"]["address"]
    except Exception as e:
        raise RuntimeError(
            f"failed to fetch loki address; j status returned {retcode!r}"
            f"with {stdout!r}, {stderr!r}"
            f"Embedded error: {e}"
        )


# We need to add dependency to loki_tester_deployment to ensure that if setup
# aborts then this test is skipped too. Else it will fail with a weird message.
async def test_log_proxy_relation_data(ops_test: OpsTest, loki_tester_deployment):  # noqa
    """Verify that loki:log-proxy has set some 'endpoints' application data."""
    retcode, stdout, stderr = await ops_test.juju("show-unit", "loki-tester/0", "--format=json")

    data = json.loads(stdout)
    lp_relation_info = data["loki-tester/0"]["relation-info"][0]

    endpoints = lp_relation_info["application-data"].get("endpoints")
    assert endpoints
    assert json.loads(endpoints)[0].get("url")


LOKI_READY_TIMEOUT = 60  # it typically takes around 15s on my machine
LOKI_READY_RETRY_SLEEP = 1

tenacious = retry(wait=wait_exponential(multiplier=1, min=10, max=60), stop=stop_after_attempt(7))


@pytest.mark.abort_on_fail
@tenacious
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

    # at this point the workload should run and fire the logs to the configured targets
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

    checks = []

    if "loki" in modes:
        assert TEST_JOB_NAME in jobs
        checks.append(assert_job_logged(TEST_JOB_NAME, LOKI_LOG_MSG, loki_address))
        stream = {"job": TEST_JOB_NAME}
        checks.append(assert_stream_equals(TEST_JOB_NAME, loki_address, stream))

    if "file" in modes:
        job = next(filter(lambda x: x.endswith("loki-tester"), jobs))
        checks.append(assert_job_logged(job, FILE_LOG_MSG, loki_address))

        extra_stream = {"filename": "/loki_tester_msgs.txt"}
        checks.append(
            assert_stream_matches_template(
                job, loki_address, stream_template, extra_stream=extra_stream
            )
        )
    if "syslog" in modes:
        job = next(filter(lambda x: x.endswith("loki-tester_syslog"), jobs))
        checks.append(assert_job_logged(job, SYSLOG_LOG_MSG, loki_address))
        checks.append(assert_stream_matches_template(job, loki_address, stream_template))

    await asyncio.gather(*checks)


juju_model_uuid_key = "juju_model_uuid"
promtail_job_template = "juju_{model_name}_{uuid}_loki-tester_loki-tester_0_loki-tester"
stream_template = {
    "juju_application": "loki-tester",
    "juju_charm": "loki-tester",
    "juju_model": "{model_name}",
    juju_model_uuid_key: "{uuid}",
    "juju_unit": "loki-tester/0",
}


def query_range(job_name: str, loki_address: str):
    params = {"query": '{job="%s"}' % job_name}
    # query_range goes from now to up to 1h ago, more
    # certain to capture something
    query_url = f"http://{loki_address}:3100/loki/api/v1/query_range"
    jsn = requests.get(query_url, params=params).json()
    return jsn["data"]["result"]


async def assert_job_logged(job_name: str, msg: str, loki_address: str):
    results = query_range(job_name, loki_address)
    assert results, f"{loki_address} returned an empty result set."
    result = results[0]
    assert result["values"][0][1] == msg


def populate_template(template, result):
    juju_model_uuid = result["stream"][juju_model_uuid_key]
    expected_stream = template.copy()
    expected_stream["juju_model"] = juju_model_name = result["stream"]["juju_model"]
    expected_stream[juju_model_uuid_key] = juju_model_uuid
    expected_stream["job"] = promtail_job_template.format(
        uuid=juju_model_uuid, model_name=juju_model_name
    )
    return expected_stream


async def assert_stream_matches_template(job_name, loki_address, template, extra_stream=None):
    results = query_range(job_name, loki_address)
    # we fill in the stream template with model uuid and model name, which vary.
    # any result will do for this, as they should be all the same.
    expected_stream = populate_template(template, results[0])

    if extra_stream:
        expected_stream.update(extra_stream)

    for result in results:
        assert result["stream"] == expected_stream


async def assert_stream_equals(job_name, loki_address, stream):
    results = query_range(job_name, loki_address)
    for result in results:
        assert result["stream"] == stream
