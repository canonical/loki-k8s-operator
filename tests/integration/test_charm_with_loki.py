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
SYSLOG_LOG_MSG = "LOG SYSLOG"
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
    await asyncio.gather(
        *(assert_logs_in_loki(mode, loki_app_name, ops_test, loki_address) for mode in modes)
    )


stream_template = {
    "job": "juju_{model_name}_{uuid}_loki-tester_loki-tester_0_loki-tester",
    "juju_application": "loki-tester",
    "juju_charm": "loki-tester",
    "juju_model": "{model_name}",
    "juju_model_uuid": "{uuid}",
    "juju_unit": "loki-tester/0",
}


async def assert_logs_in_loki(mode: str, loki_app_name: str, ops_test: OpsTest, loki_address: str):
    url = f"http://{loki_address}:3100"

    async def query_job(job_name, attempt=0):
        params = {"query": '{job="%s"}' % job_name}
        # query_range goes from now to up to 1h ago, more
        # certain to capture something
        query_url = f"{url}/loki/api/v1/query_range"
        jsn = requests.get(query_url, params=params).json()
        results = jsn["data"]["result"]
        if not results:
            raise ValueError(f"{query_url} returned an empty result set.")
        result = results[0]
        return result

    if mode == "loki":
        res = await query_job(TEST_JOB_NAME)
        assert res["stream"] == {"job": TEST_JOB_NAME}
        assert res["values"][0][1] == LOKI_LOG_MSG
        return

    if mode == "file":
        suffix = "_loki-tester"
        msg = FILE_LOG_MSG
        extra_stream = {"filename": "/loki_tester_msgs.txt"}
        job_suffix = ""
    else:  # syslog mode
        suffix = "_loki-tester_syslog"
        # need to prefix BOM \ufeff because syslog msgs are encoded in some
        # special way. 'utf-8-sig' perhaps?
        msg = "\ufeff" + SYSLOG_LOG_MSG
        extra_stream = {}
        job_suffix = "_syslog"

    # get the job name for the log stream
    labels = requests.get(f"{url}/loki/api/v1/label/job/values").json().get("data")
    if not labels:
        raise RuntimeError("no jobs present: nothing was logged yet.")
    try:
        job_label = next(filter(lambda x: x.endswith(suffix), labels))
    except StopIteration:
        raise RuntimeError(f"expected label with suffix {suffix} not " f"found in" f"{labels}.")

    print("job label:", job_label)

    res = await query_job(job_label)
    juju_model_uuid_key = "juju_model_uuid"
    juju_model_uuid = res["stream"][juju_model_uuid_key]
    expected_stream = stream_template.copy()
    expected_stream.update(extra_stream)
    expected_stream["juju_model"] = juju_model_name = res["stream"]["juju_model"]
    expected_stream[juju_model_uuid_key] = juju_model_uuid
    expected_stream["job"] = (
        expected_stream["job"].format(uuid=juju_model_uuid, model_name=juju_model_name)
        + job_suffix
    )

    assert res["stream"] == expected_stream
    assert res["values"][0][1] == msg
