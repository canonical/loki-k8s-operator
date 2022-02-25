import asyncio
import json
import sys
import time
from subprocess import Popen, PIPE

import requests

import pytest

from tests.integration.loki_tester.lib.charms.loki_k8s.v0.loki_push_api import (
    WORKLOAD_BINARY_DIR, BINARY_FILE_NAME, WORKLOAD_CONFIG_DIR,
    WORKLOAD_CONFIG_FILE_NAME, WORKLOAD_CONFIG_PATH
)
from pytest_operator.plugin import OpsTest
from helpers import IPAddressWorkaround, all_combinations, is_loki_up

TEST_JOB_NAME = 'test-job'
SYSLOG_LOG_MSG = "LOG SYSLOG"
LOKI_LOG_MSG = "LOG LOKI"
FILE_LOG_MSG = "LOG FILE"


async def run_in_loki_tester(ops_test: OpsTest, cmd):
    cmd_line = f"juju ssh --container loki-tester loki-tester/0 {cmd}"
    return await ops_test.run(*cmd_line.split(" "))


async def assert_file_exists(ops_test, file_path, file_name):
    retcode, stdout, stderr = await run_in_loki_tester(
        ops_test, f'ls -l {file_path}{file_name}| grep {file_name}')
    assert stdout
    assert not stderr
    assert retcode == 0


async def test_logpy_is_in_workload_container(
        ops_test: OpsTest, loki_tester_deployment
):
    """verify that log.py is in the container
    """
    # this could be done in a smarter way I guess
    await assert_file_exists(ops_test, '/', 'log.py')


async def test_promtail_files_are_in_workload_container(
        ops_test: OpsTest, loki_tester_deployment
):
    """verify that the promload binary and the config are where they should,
    """
    await assert_file_exists(
        ops_test, WORKLOAD_BINARY_DIR + '/', BINARY_FILE_NAME)
    await assert_file_exists(
        ops_test, WORKLOAD_CONFIG_DIR + '/', WORKLOAD_CONFIG_FILE_NAME)


async def test_promtail_is_running_in_workload_container(
        ops_test: OpsTest, loki_tester_deployment
):
    """verify that the promtail process is running
    """
    await run_in_loki_tester(ops_test, 'apt update -y && apt install procps -y')
    retcode, stdout, stderr = await run_in_loki_tester(
        ops_test, 'ps -aux | grep promtail')
    cmd = f"{BINARY_FILE_NAME} -config.file={WORKLOAD_CONFIG_PATH}"
    assert cmd in stdout


@pytest.mark.parametrize(
    'modes',
    all_combinations(
        ('loki',)
    )
)
@pytest.mark.abort_on_fail
async def test_loki_scraping_with_promtail(
        modes: str, ops_test: OpsTest, loki_tester_deployment
):
    """Test the core loki functionality + promtail on several log output
    scenarios.
    """
    app_names = loki_app_name, loki_tester_app_name = loki_tester_deployment

    # at this point the workload should run and fire the logs to the configured targets
    print(f'configuring {loki_tester_app_name} to {modes}')
    await ops_test.juju('config', loki_tester_app_name, f'log-to={modes}')

    await ops_test.model.wait_for_idle(apps=[loki_tester_app_name],
                                       status="active")

    # obtain the loki cluster IP to make direct api calls
    retcode, stdout, stderr = await ops_test.juju("status", "--format=json")
    try:
        jsn = json.loads(stdout)
        loki_address = jsn["applications"][loki_app_name]["units"][
            f"{loki_app_name}/0"]["address"]
    except Exception as e:
        raise RuntimeError(
            f"failed to fetch loki address; j status returned {retcode!r}"
            f"with {stdout!r}, {stderr!r}"
            f"Embedded error: {e}"
        )

    await asyncio.gather(*(
        assert_logs_in_loki(mode, loki_app_name, ops_test, loki_address)
        for mode in modes.split(','))
                         )


stream_template = {
    "job": "juju_{model_name}_{uuid}_loki-tester_loki-tester_0_loki-tester",
    "juju_application": "loki-tester",
    "juju_charm": "loki-tester",
    "juju_model": "{model_name}",
    "juju_model_uuid": "{uuid}",
    "juju_unit": "loki-tester/0",
}
WAIT = 1.0
MAX_QUERY_RETRIES = 5


async def assert_logs_in_loki(mode: str, loki_app_name: str, ops_test: OpsTest,
                              loki_address: str):
    url = f"http://{loki_address}:3100"

    def query_job(job_name, attempt=0):
        print(f'Trying to query loki; attempt #{attempt}.')
        params = {'query': '{job="%s"}' % job_name}
        # query_range goes from now to up to 1h ago, more
        # certain to capture something
        query_url = f"{url}/loki/api/v1/query_range"
        jsn = requests.get(query_url, params=params).json()
        results = jsn['data']['result']
        labels = requests.get(f"{url}/loki/api/v1/labels").json().get('data',
                                                                      '<no data!?>')
        job_values = requests.get(
            f"{url}/loki/api/v1/label/job/values").json().get('data',
                                                              '<no data!?>')

        if not results:
            if attempt > MAX_QUERY_RETRIES:
                raise RuntimeError(
                    f'timeout attempting to query loki '
                    f'for {job_name} ({WAIT * attempt}s) at url:{query_url!r} with params={params};'
                    f'available labels = {labels!r};'
                    f'values for job = {job_values!r}')

            print(f'Loki received no logs yet; retry in {WAIT}')
            print(f"labels: {labels!r}; job values: {job_values!r}")
            time.sleep(WAIT)

            return query_job(job_name, attempt + 1)

        print(f"Loki query successful after {attempt} attempts; "
              f"{WAIT * attempt} seconds elapsed")
        return results[0]

    if mode == 'loki':
        res = query_job(TEST_JOB_NAME)
        assert res["stream"] == {'job': TEST_JOB_NAME}
        assert res["values"][0][1] == LOKI_LOG_MSG
        return

    if mode == 'file':
        suffix = "_loki-tester"
        msg = FILE_LOG_MSG
        extra_stream = {'filename': "/loki_tester_msgs.txt"}
    else:  # syslog mode
        suffix = "_syslog"
        msg = SYSLOG_LOG_MSG
        extra_stream = {}

    # get the job name for the log stream
    labels = requests.get(f"{url}/loki/api/v1/label/job/values"
                          ).json()["data"]
    try:
        job_label = next(filter(lambda x: x.endswith(suffix), labels))
    except StopIteration:
        raise RuntimeError(f'expected label with suffix {suffix} not found in'
                           f'{labels}.')

    print('job label:', job_label)

    res = query_job(job_label)
    juju_model_uuid_key = "juju_model_uuid"
    juju_model_uuid = res["stream"][juju_model_uuid_key]
    expected_stream = stream_template.copy()
    expected_stream.update(extra_stream)
    expected_stream['juju_model'] = juju_model_name = res['stream'][
        'juju_model']
    expected_stream[juju_model_uuid_key] = juju_model_uuid
    expected_stream["job"] = expected_stream["job"].format(
        uuid=juju_model_uuid,
        model_name=juju_model_name)

    assert res["stream"] == expected_stream
    assert res["values"][0][1] == msg
