# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import urllib.request
from typing import List

import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


async def get_unit_address(ops_test, app_name: str, unit_num: int) -> str:
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def is_loki_up(ops_test, app_name, num_units=1) -> bool:
    # Sometimes get_unit_address returns a None, no clue why, so looping until it's not
    addresses = [""] * num_units
    while not all(addresses):
        addresses = [await get_unit_address(ops_test, app_name, i) for i in range(num_units)]
    logger.info("Loki addresses: %s", addresses)

    def get(url) -> bool:
        response = urllib.request.urlopen(url, data=None, timeout=2.0)
        return response.code == 200 and "version" in json.loads(response.read())

    return all(get(f"http://{address}:3100/loki/api/v1/status/buildinfo") for address in addresses)


async def loki_rules(ops_test, app_name) -> dict:
    address = await get_unit_address(ops_test, app_name, 0)
    url = f"http://{address}:3100"

    try:
        response = urllib.request.urlopen(f"{url}/loki/api/v1/rules", data=None, timeout=2.0)
        if response.code == 200:
            return yaml.safe_load(response.read())
        return {}
    except urllib.error.HTTPError:
        return {}


async def loki_alerts(ops_test: str, app_name: str, unit_num: int = 0, retries: int = 3) -> dict:
    r"""Get a list of alerts from a Prometheus-compatible endpoint.

    Results look like:
        {
          "data": {
              "groups": [
                  {
                      "rules": [
                          {
                              "alerts": [
                                  {
                                      "activeAt": "2018-07-04T20:27:12.60602144+02:00",
                                      "annotations": {
                                          "summary": "High request latency"
                                      },
                                      "labels": {
                                          "alertname": "HighRequestLatency",
                                          "severity": "page"
                                      },
                                      "state": "firing",
                                      "value": "1e+00"
                                  }
                              ],
                              "annotations": {
                                  "summary": "High request latency"
                              },
                              "duration": 600,
                              "health": "ok",
                              "labels": {
                                  "severity": "page"
                              },
                              "name": "HighRequestLatency",
                              "query": "job:request_latency_seconds:mean5m{job=\"myjob\"} > 0.5",
                              "type": "alerting"
                          },
                          {
                              "health": "ok",
                              "name": "job:http_inprogress_requests:sum",
                              "query": "sum by (job) (http_inprogress_requests)",
                              "type": "recording"
                          }
                      ],
                      "file": "/rules.yaml",
                      "interval": 60,
                      "limit": 0,
                      "name": "example"
                  }
              ]
          },
          "status": "success"
        }
    """
    address = await get_unit_address(ops_test, app_name, unit_num)
    url = f"http://{address}:3100/prometheus/api/v1/alerts"

    # Retry since the endpoint may not _immediately_ return valid data
    while not (
        alerts := json.loads(urllib.request.urlopen(url, data=None, timeout=2).read())["data"][
            "alerts"
        ]
    ):
        retries -= 1
        if retries > 0:
            await asyncio.sleep(2)
        else:
            break

    return alerts


async def get_alertmanager_alerts(ops_test: OpsTest, unit_name, unit_num, retries=3) -> List[dict]:
    """Get a list of alerts.

    Response looks like this:
    {
        'annotations': {'description': 'test-charm-...', 'summary': 'Instance test-charm-...'},
        'endsAt': '2021-09-03T21:03:59.658Z',
        'fingerprint': '4a0016cc12a07903',
        'receivers': [{'name': 'pagerduty'}],
        'startsAt': '2021-09-03T19:37:59.658Z',
        'status': {'inhibitedBy': [], 'silencedBy': [], 'state': 'active'},
        'updatedAt': '2021-09-03T20:59:59.660Z',
        'generatorURL': 'http://prometheus-0:9090/...',
        'labels': {
            'alertname': 'AlwaysFiring',
            'instance': 'test-charm-...',
            'job': 'juju_test-charm-...',
            'juju_application': 'tester', 'juju_model': 'test-charm-...',
            'juju_model_uuid': '...',
            'juju_unit': 'tester-0',
            'severity': 'Low',
            'status': 'testing'
        }
    }
    """
    address = await get_unit_address(ops_test, unit_name, unit_num)
    url = f"http://{address}:9093/api/v2/alerts"
    while not (alerts := json.loads(urllib.request.urlopen(url, data=None, timeout=2).read())):
        retries -= 1
        if retries > 0:
            await asyncio.sleep(2)
        else:
            break

    return alerts


class ModelConfigChange:
    """Context manager for temporarily changing a model config option."""

    def __init__(self, ops_test: OpsTest, config: dict):
        self.ops_test = ops_test
        self.change_to = config

    async def __aenter__(self):
        """On entry, the config is set to the user provided custom values."""
        config = await self.ops_test.model.get_config()
        self.revert_to = {k: config[k] for k in self.change_to.keys()}
        await self.ops_test.model.set_config(self.change_to)
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        """On exit, the modified config options are reverted to their original values."""
        await self.ops_test.model.set_config(self.revert_to)
