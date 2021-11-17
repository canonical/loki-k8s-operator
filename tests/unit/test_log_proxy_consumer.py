# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import textwrap
import unittest
from unittest.mock import patch

from charms.loki_k8s.v0.log_proxy import LogProxyConsumer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness


def pull_empty_fake_file(self, _):
    return FakeFile("")


class FakeFile:
    def __init__(self, content="PEPE"):
        self.content = content

    def read(self, *args, **kwargs):
        return self.content


METADATA = {
    "model": "consumer-model",
    "model_uuid": "qwerty-1234",
    "application": "promtail",
    "charm_name": "charm-k8s",
}

LOG_FILES = [
    "/var/log/apache2/access.log",
    "/var/log/alternatives.log",
    "/var/log/test.log",
]

CONFIG: dict = {"clients": []}


WORKLOAD_BINARY_DIR = "/opt/promtail"
WORKLOAD_POSITIONS_PATH = "{}/positions.yaml".format(WORKLOAD_BINARY_DIR)

HTTP_LISTEN_PORT = 9080
GRPC_LISTEN_PORT = 9095

os.environ["JUJU_MODEL_NAME"] = "PEPEEEE"


class ConsumerCharm(CharmBase):
    _stored = StoredState()
    metadata_yaml = textwrap.dedent(
        """
        name: loki-k8s
        requires:
          log_proxy:
            interface: loki_push_api
            optional: true
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self._log_proxy = LogProxyConsumer(
            charm=self, log_files=LOG_FILES, container_name="consumercharm"
        )


class TestLogProxyConsumer(unittest.TestCase):
    @patch("charms.loki_k8s.v0.log_proxy.LogProxyConsumer._get_container")
    def setUp(self, mock_container):
        mock_container.return_value = True

        self.harness = Harness(ConsumerCharm, meta=ConsumerCharm.metadata_yaml)
        self.harness.set_model_info(name="MODEL", uuid="123456")
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test__cli_args(self):
        expected_args = "-config.file=/etc/promtail/promtail_config.yaml"
        self.assertEqual(self.harness.charm._log_proxy._cli_args, expected_args)

    def test__initial_config(self):
        expected = {
            "server": {"http_listen_port": 9080, "grpc_listen_port": 9095},
            "positions": {"filename": "/opt/promtail/positions.yaml"},
            "scrape_configs": [
                {
                    "job_name": "system",
                    "static_configs": [
                        {
                            "targets": ["localhost"],
                            "labels": {
                                "job": "juju_MODEL_123456_loki-k8s",
                                "__path__": "/var/log/apache2/access.log",
                            },
                        },
                        {
                            "targets": ["localhost"],
                            "labels": {
                                "job": "juju_MODEL_123456_loki-k8s",
                                "__path__": "/var/log/alternatives.log",
                            },
                        },
                        {
                            "targets": ["localhost"],
                            "labels": {
                                "job": "juju_MODEL_123456_loki-k8s",
                                "__path__": "/var/log/test.log",
                            },
                        },
                    ],
                }
            ],
        }
        self.assertEqual(self.harness.charm._log_proxy._initial_config, expected)
