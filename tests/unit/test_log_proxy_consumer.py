# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap
import unittest
from unittest.mock import patch

from charms.loki_k8s.v0.log_proxy import LogProxyConsumer
from deepdiff import DeepDiff  # type: ignore
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness

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

INIT_CONFIG: dict = {"clients": []}

CONFIG = {
    "clients": [{"url": "http://10.20.30.1:3500/loki/api/v1/push"}],
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

WORKLOAD_BINARY_DIR = "/opt/promtail"
WORKLOAD_POSITIONS_PATH = "{}/positions.yaml".format(WORKLOAD_BINARY_DIR)

HTTP_LISTEN_PORT = 9080
GRPC_LISTEN_PORT = 9095


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

    def test__add_client(self):
        agent_url1 = "http://10.20.30.1:3500/loki/api/v1/push"
        agent_url2 = "http://10.20.30.2:3500/loki/api/v1/push"

        expected_config = CONFIG.copy()
        expected_config["clients"] = [{"url": agent_url1}, {"url": agent_url2}]
        self.harness.charm._log_proxy._add_client(CONFIG, agent_url1)
        conf = self.harness.charm._log_proxy._add_client(CONFIG, agent_url2)
        self.assertEqual(DeepDiff(conf, expected_config, ignore_order=True), {})

        CONFIG.pop("clients")
        expected_config2 = CONFIG.copy()
        expected_config2["clients"] = [{"url": agent_url1}, {"url": agent_url2}]
        self.harness.charm._log_proxy._add_client(CONFIG, agent_url1)
        conf1 = self.harness.charm._log_proxy._add_client(CONFIG, agent_url2)
        self.assertEqual(DeepDiff(conf1, expected_config2, ignore_order=True), {})

    def test__remove_client(self):
        agent_url1 = "http://10.20.30.1:3500/loki/api/v1/push"
        agent_url2 = "http://10.20.30.2:3500/loki/api/v1/push"
        CONFIG["clients"] = [{"url": agent_url1}, {"url": agent_url2}]
        expected_config: dict = CONFIG.copy()
        expected_config["clients"].pop(0)

        conf = self.harness.charm._log_proxy._remove_client(CONFIG, agent_url1)
        self.assertEqual(DeepDiff(conf, expected_config, ignore_order=True), {})
