# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap
import unittest
from unittest.mock import patch

from charms.loki_k8s.v0.log_proxy import LogProxyConsumer, PromtailDigestError
from deepdiff import DeepDiff  # type: ignore
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.model import Container
from ops.testing import Harness

LOG_FILES = [
    "/var/log/apache2/access.log",
    "/var/log/alternatives.log",
    "/var/log/test.log",
]

HTTP_LISTEN_PORT = 9080
GRPC_LISTEN_PORT = 9095

CONFIG = {
    "clients": [{"url": "http://10.20.30.1:3500/loki/api/v1/push"}],
    "server": {"http_listen_port": HTTP_LISTEN_PORT, "grpc_listen_port": GRPC_LISTEN_PORT},
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


class ConsumerCharm(CharmBase):
    _stored = StoredState()
    metadata_yaml = textwrap.dedent(
        """
        name: loki-k8s
        containers:
          loki:
            resource: loki-image
          promtail:
            resource: promtail-image
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

    def test__cli_args_with_config_file_parameter(self):
        self.assertIn("-config.file=", self.harness.charm._log_proxy._cli_args)

    def test__initial_config_sections(self):
        expected_sections = {"positions", "scrape_configs", "server"}
        self.assertEqual(set(self.harness.charm._log_proxy._initial_config), expected_sections)

    def test__add_client_with_client_section(self):
        agent_url1 = "http://10.20.30.1:3500/loki/api/v1/push"
        agent_url2 = "http://10.20.30.2:3500/loki/api/v1/push"

        expected_config = CONFIG.copy()
        expected_config["clients"] = [{"url": agent_url1}, {"url": agent_url2}]
        self.harness.charm._log_proxy._add_client(CONFIG, agent_url1)
        conf = self.harness.charm._log_proxy._add_client(CONFIG, agent_url2)
        self.assertEqual(DeepDiff(conf, expected_config, ignore_order=True), {})

    def test__add_client_without_client_section(self):
        agent_url1 = "http://10.20.30.1:3500/loki/api/v1/push"
        agent_url2 = "http://10.20.30.2:3500/loki/api/v1/push"
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

    def test__get_container_container_name_not_exist(self):
        # Container do not exist
        container_name = "loki_container"

        with self.assertRaises(PromtailDigestError) as context:
            self.harness.charm._log_proxy._get_container(container_name)

        self.assertEqual(f"container '{container_name}' not found", str(context.exception))

    def test__get_container_container_name_exist(self):
        # Container exist
        container_name = "loki"
        self.assertIs(
            type(self.harness.charm._log_proxy._get_container(container_name)), Container
        )

    def test__get_container_more_than_one_container(self):
        # More than 1 container in Pod
        container_name = ""
        with self.assertRaises(PromtailDigestError):
            self.harness.charm._log_proxy._get_container(container_name)
