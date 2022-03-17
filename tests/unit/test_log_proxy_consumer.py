# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap
import unittest
from hashlib import sha256
from unittest.mock import MagicMock, mock_open, patch

from charms.loki_k8s.v0.loki_push_api import ContainerNotFoundError, LogProxyConsumer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.model import Container
from ops.testing import Harness

LOG_FILES = ["/var/log/apache2/access.log", "/var/log/alternatives.log", "/var/log/test.log"]

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
        self._stored.set_default(invalid_events=0)
        self._log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=True
        )

        self.framework.observe(
            self._log_proxy.on.promtail_digest_error, self._register_promtail_error
        )

    def _register_promtail_error(self, _):
        self._stored.invalid_events += 1


class ConsumerCharmSyslogDisabled(ConsumerCharm):
    def __init__(self, *args, **kwargs):
        super(ConsumerCharm, self).__init__(*args)
        self._port = 3100
        self._log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=False
        )


class TestLogProxyConsumer(unittest.TestCase):
    def setUp(self):

        self.harness = Harness(ConsumerCharm, meta=ConsumerCharm.metadata_yaml)
        self.harness.set_model_info(name="MODEL", uuid="123456")
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test__cli_args_with_config_file_parameter(self):
        self.assertIn("-config.file=", self.harness.charm._log_proxy._cli_args)

    def test__initial_config_sections(self):
        expected_sections = {"clients", "positions", "scrape_configs", "server"}
        self.assertEqual(set(self.harness.charm._log_proxy._promtail_config), expected_sections)

    def test__initial_config_jobs(self):
        expected_jobs = {"system", "syslog"}
        self.assertEqual(
            {
                x["job_name"]
                for x in self.harness.charm._log_proxy._promtail_config["scrape_configs"]
            },
            expected_jobs,
        )

    def test__initial_config_labels(self):
        for job in self.harness.charm._log_proxy._promtail_config["scrape_configs"]:
            if job["job_name"] == "system":
                expected = {
                    "__path__",
                    "job",
                    "juju_application",
                    "juju_charm",
                    "juju_unit",
                    "juju_model",
                    "juju_model_uuid",
                }
                for static_config in job["static_configs"]:
                    self.assertEqual(set(static_config["labels"]), expected)
            if job["job_name"] == "syslog":
                expected = {
                    "job",
                    "juju_application",
                    "juju_charm",
                    "juju_unit",
                    "juju_model",
                    "juju_model_uuid",
                }
                self.assertEqual(set(job["syslog"]["labels"]), expected)

    def test__add_client(self):
        expected_clients = {
            "http://10.20.30.1:3500/loki/api/v1/push",
            "http://10.20.30.2:3500/loki/api/v1/push",
        }
        rel_id = self.harness.add_relation("log-proxy", "agent")
        self.harness.add_relation_unit(rel_id, "agent/0")
        self.harness.add_relation_unit(rel_id, "agent/1")
        self.harness.update_relation_data(
            rel_id,
            "agent",
            {
                "endpoints": '[{"url": "http://10.20.30.1:3500/loki/api/v1/push"}, {"url": "http://10.20.30.2:3500/loki/api/v1/push"}]'
            },
        )
        self.assertEqual(
            {x["url"] for x in self.harness.charm._log_proxy._clients_list()}, expected_clients
        )

    def test__empty_clients_list(self):
        # Ensure we do not raise an exception if the clients list is empty
        rel_id = self.harness.add_relation("log-proxy", "agent")
        self.harness.add_relation_unit(rel_id, "agent/0")
        self.assertEqual(self.harness.charm._log_proxy._clients_list(), [])

    def test__get_container_container_name_not_exist(self):
        # Container do not exist
        container_name = "loki_container"
        self.harness.charm._log_proxy._get_container(container_name)

        self.assertEqual(self.harness.charm._stored.invalid_events, 1)

    def test__get_container_container_name_exist(self):
        # Container exist
        container_name = "loki"
        self.assertIs(
            type(self.harness.charm._log_proxy._get_container(container_name)), Container
        )

    def test__get_container_more_than_one_container(self):
        # More than 1 container in Pod
        container_name = ""
        with self.assertRaises(ContainerNotFoundError):
            self.harness.charm._log_proxy._get_container(container_name)

    def test__sha256sums_matches_match(self):
        read_data = str.encode("Bytes in the file")
        sha256sum = sha256(read_data).hexdigest()
        mocked_open = mock_open(read_data=read_data)

        with patch("builtins.open", mocked_open, create=True):
            self.assertTrue(self.harness.charm._log_proxy._sha256sums_matches("file", sha256sum))

    def test__sha256sums_matches_do_not_match(self):
        read_data = str.encode("Bytes in the file")
        sha256sum = "qwertyfakesha256"
        mocked_open = mock_open(read_data=read_data)

        with patch("builtins.open", mocked_open, create=True):
            self.assertFalse(self.harness.charm._log_proxy._sha256sums_matches("file", sha256sum))

    def test__sha256sums_matches_file_not_found(self):
        read_data = str.encode("Bytes in the file")
        sha256sum = sha256(read_data).hexdigest()
        mocked_open = mock_open(read_data=read_data)
        mocked_open.side_effect = FileNotFoundError

        with patch("builtins.open", mocked_open, create=True):
            self.assertFalse(self.harness.charm._log_proxy._sha256sums_matches("file", sha256sum))

    @patch("pathlib.Path.is_file")
    def test__is_promtail_binary_in_charm_not(self, mock_is_file):
        mock_is_file.return_value = False
        self.assertFalse(self.harness.charm._log_proxy._is_promtail_binary_in_charm())

    @patch("pathlib.Path.is_file")
    def test__is_promtail_binary_in_workload_yes(self, mock_is_file):
        mock_is_file.return_value = True
        self.assertTrue(self.harness.charm._log_proxy._is_promtail_binary_in_charm())

    def test__is_promtail_attached_name_error(self):
        self.harness.charm._log_proxy._charm.model.resources.fetch = MagicMock(
            side_effect=NameError("invalid resource name")
        )
        self.assertFalse(self.harness.charm._log_proxy._is_promtail_attached())

    def test__is_promtail_attached_model(self):
        self.harness.charm._log_proxy._charm.model.resources.fetch = MagicMock(
            return_value="promtail"
        )
        self.harness.charm._log_proxy._container = MagicMock(return_value=True)
        mocked_open = mock_open()

        with patch("builtins.open", mocked_open, create=True):
            self.assertTrue(self.harness.charm._log_proxy._is_promtail_attached())

            with self.assertLogs(level="INFO") as logger:
                self.harness.charm._log_proxy._is_promtail_attached()
                self.assertEqual(
                    sorted(logger.output),
                    [
                        "INFO:charms.loki_k8s.v0.loki_push_api:Promtail binary file has been obtained from an attached resource."
                    ],
                )

    def test__promtail_must_be_downloaded_not_in_workload(self):
        self.harness.charm._log_proxy._is_promtail_binary_in_charm = MagicMock(return_value=False)
        self.assertTrue(self.harness.charm._log_proxy._promtail_must_be_downloaded())

    def test__promtail_must_be_downloaded_in_workload_sha256_dont_match(self):
        self.harness.charm._log_proxy._is_promtail_binary_in_workload = MagicMock(
            return_value=True
        )
        self.harness.charm._log_proxy._get_promtail_bin_from_workload = MagicMock(
            return_value=True
        )
        self.harness.charm._log_proxy._sha256sums_matches = MagicMock(return_value=False)
        self.assertTrue(self.harness.charm._log_proxy._promtail_must_be_downloaded())

    def test__promtail_must_be_downloaded_in_workload_sha256_match(self):
        self.harness.charm._log_proxy._is_promtail_binary_in_charm = MagicMock(return_value=True)
        self.harness.charm._log_proxy._sha256sums_matches = MagicMock(return_value=True)

        with self.assertLogs(level="DEBUG") as logger:
            self.assertFalse(self.harness.charm._log_proxy._promtail_must_be_downloaded())
            self.assertEqual(
                sorted(logger.output),
                [
                    "DEBUG:charms.loki_k8s.v0.loki_push_api:Promtail binary file is already in the the charm container."
                ],
            )


class TestLogProxyConsumerWithoutSyslog(unittest.TestCase):
    @patch("charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._get_container")
    def setUp(self, mock_container):
        mock_container.return_value = True

        self.harness = Harness(ConsumerCharmSyslogDisabled, meta=ConsumerCharm.metadata_yaml)
        self.harness.set_model_info(name="MODEL", uuid="123456")
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test__syslog_not_enabled(self):
        self.assertTrue(
            "syslog"
            not in {
                x["job_name"]
                for x in self.harness.charm._log_proxy._promtail_config["scrape_configs"]
            }
        )
