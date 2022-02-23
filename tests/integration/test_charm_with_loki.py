import asyncio
import json
from subprocess import Popen, PIPE
import requests

import pytest
from tests.integration.loki_tester.src.log import (
    SYSLOG_LOG_MSG, LOKI_LOG_MSG, FILE_LOG_MSG)
from pytest_operator.plugin import OpsTest
from helpers import IPAddressWorkaround, all_combinations, is_loki_up


@pytest.mark.parametrize(
    'modes',
    all_combinations(
        ('syslog', 'loki', 'file')
    )
)
@pytest.mark.abort_on_fail
async def test_loki_scraping_with_promtail(
        modes: str, ops_test: OpsTest, loki_tester_deployment
):
    """Test the core loki functionality + promtail on several log output
    scenarios.
    """
    loki_app_name, loki_tester_app_name = loki_tester_deployment
    # we configure the loki tester app
    await asyncio.gather(
        ops_test.run(f'config {loki_tester_app_name} {modes}'),
        ops_test.run(f'expose {loki_app_name}/0')
    )

    # obtain the loki cluster IP to make direct api calls
    cmd = Popen(f"juju status {loki_tester_app_name} --format=json".split(" "),
                stdout=PIPE)
    jsn = json.loads(cmd.stdout.read().decode('utf-8'))
    ip = jsn["applications"][f"{loki_tester_app_name}"]["units"] \
        [f"{loki_tester_app_name}/0"]["address"]

    await asyncio.gather((
        assert_logs_in_loki(mode, loki_app_name, ops_test, ip)
        for mode in modes.split(','))
    )

stream_template = {
    "job": "juju_{model_name}_{uuid}_loki-tester_loki-tester_0_loki-tester",
     "juju_application": "loki-tester",
     "juju_charm": "loki-tester",
     "juju_model": "cos",
     "juju_model_uuid": "{uuid}",
     "juju_unit": "loki-tester/0",
}

async def assert_logs_in_loki(mode: str, loki_app_name: str, ops_test: OpsTest,
                              ip: str):
    url = f"http://{ip}:3100"

    def query_job(job_name):
        jsn = requests.get(f"{url}/loki/api/v1/query",
                           params={'query': '{job="{%s}"}' % job_name}
                           ).json()
        return jsn['data']['result']

    if mode == 'loki':
        res = query_job('job-test')
        assert res[0]["stream"] == {'job': 'test-job'}
        assert res[0]["values"][0][1] == LOKI_LOG_MSG
        return

    if mode == 'loki':
        suffix = "_loki-tester"
        msg = LOKI_LOG_MSG
    else: # syslog mode
        suffix = "_syslog"
        msg = SYSLOG_LOG_MSG

    # get the job name for the log stream
    labels = requests.get(f"{url}/loki/api/v1/label/job/values"
                          ).json()["data"]
    job_label = next(filter(lambda x: x.endswith(suffix), labels))

    res = query_job(job_label)
    jmuuid_key = "juju_model_uuid"
    jmuuid = res[0]["stream"][jmuuid_key]
    expected_stream = stream_template.copy()
    expected_stream[jmuuid_key] = jmuuid
    expected_stream["job"] = expected_stream["job"].format(
        uuid=jmuuid,
        model_name=res[0]["stream"]["juju_model"])

    assert res[0]["stream"] == expected_stream
    assert res[0]["values"][0][1] == msg