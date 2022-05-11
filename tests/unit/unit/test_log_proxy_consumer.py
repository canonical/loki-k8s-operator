# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
import textwrap
import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import mock_open, patch

import ops
from charms.loki_k8s.v0 import loki_push_api
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.model import Container
from ops.pebble import PathError
from ops.testing import Harness

ops.testing.SIMULATE_CAN_CONNECT = True
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

PROMTAIL_INFO = {
    "filename": "promtail-linux-amd64",
    "zipsha": "978391a174e71cfef444ab9dc012f95d5d7eae0d682eaf1da2ea18f793452031",
    "binsha": "00ed6a4b899698abc97d471c483a6a7e7c95e761714f872eb8d6ffd45f3d32e6",
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
          log-proxy:
            interface: loki_push_api
            optional: true
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self._stored.set_default(invalid_events=0)
        self.log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=True
        )

        self.framework.observe(
            self.log_proxy.on.promtail_digest_error, self._register_promtail_error
        )

    def _register_promtail_error(self, _):
        self._stored.invalid_events += 1


class ConsumerCharmSyslogDisabled(ConsumerCharm):
    def __init__(self, *args, **kwargs):
        super(ConsumerCharm, self).__init__(*args)
        self._port = 3100
        self.log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=False
        )


class ConsumerCharmWithPromtailResource(CharmBase):
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
          log-proxy:
            interface: loki_push_api
            optional: true
        resources:
          promtail-bin:
            type: file
            description: promtail binary
            filename: promtail-linux-amd64
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self._stored.set_default(invalid_events=0)
        self.log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=True
        )


class TestLogProxyConsumer(unittest.TestCase):
    def setUp(self):

        self.harness = Harness(ConsumerCharm, meta=ConsumerCharm.metadata_yaml)
        self.harness.set_model_info(name="MODEL", uuid="123456")
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

    def test__cli_args_with_config_file_parameter(self):
        self.assertIn("-config.file=", self.harness.charm.log_proxy._cli_args)

    def test__config_sections_match_expected(self):
        expected_sections = {"clients", "positions", "scrape_configs", "server"}
        self.assertEqual(set(self.harness.charm.log_proxy._promtail_config), expected_sections)

    def test__config_jobs_match_expected(self):
        expected_jobs = {"system", "syslog"}
        self.assertEqual(
            {
                x["job_name"]
                for x in self.harness.charm.log_proxy._promtail_config["scrape_configs"]
            },
            expected_jobs,
        )

    def test__config_labels_match_expected(self):
        for job in self.harness.charm.log_proxy._promtail_config["scrape_configs"]:
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

    def test__config_syslog_labels_match_expected(self):
        for job in self.harness.charm.log_proxy._promtail_config["scrape_configs"]:
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

    def test__client_list_matches_expected(self):
        expected_clients = {
            "http://10.20.30.1:3500/loki/api/v1/push",
            "http://10.20.30.2:3500/loki/api/v1/push",
        }
        rel_id = self.harness.add_relation("log-proxy", "agent")
        self.harness.add_relation_unit(rel_id, "agent/0")
        self.harness.add_relation_unit(rel_id, "agent/1")

        for i in range(2):
            unit = f"agent/{i}"
            endpoint = f"http://10.20.30.{i+1}:3500/loki/api/v1/push"
            data = json.dumps({"url": f"{endpoint}"})
            self.harness.add_relation_unit(rel_id, unit)
            self.harness.update_relation_data(
                rel_id,
                unit,
                {"endpoint": data},
            )
        self.assertEqual(
            {x["url"] for x in self.harness.charm.log_proxy._clients_list()}, expected_clients
        )

    def test__invalid_container_name_fails(self):
        self.harness.charm.log_proxy._get_container("not_present")
        self.assertEqual(self.harness.charm._stored.invalid_events, 1)

    def test__valid_container_name_works(self):
        container_name = "loki"
        self.assertIs(type(self.harness.charm.log_proxy._get_container(container_name)), Container)

    def test__empty_lookup_with_more_than_one_container_fails(self):
        # More than 1 container in Pod and the name is not specified
        self.harness.charm.log_proxy._get_container()
        self.assertEqual(self.harness.charm._stored.invalid_events, 1)

    def test__sha256sum_is_false_with_file_not_found(self):
        mocked_open = mock_open()
        mocked_open.side_effect = FileNotFoundError

        with patch("builtins.open", mocked_open):
            self.assertFalse(self.harness.charm.log_proxy._sha256sums_matches("file", "foo"))

    @patch("charms.loki_k8s.v0.loki_push_api.BINARY_DIR", mkdtemp(prefix="logproxy-unittest"))
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._download_and_push_promtail_to_workload"
    )
    def test__promtail_sha256sum_mismatch_downloads_new(self, mock_download):
        # To correctly patch out a constant, we had to import the whole module and patch
        # as above. A MagicMock() or Mock() doesn't otherwise work for a bare variable.
        #
        # The alternative is to put this entire test in a `with:` block
        tmpdir = loki_push_api.BINARY_DIR

        # Set up an initial state with a sum that won't match
        fake_promtail = os.path.join(tmpdir, PROMTAIL_INFO["filename"])
        fake_content = "dummy_data".encode()
        Path(fake_promtail).write_bytes(fake_content)

        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm.log_proxy._obtain_promtail(PROMTAIL_INFO)
            self.assertTrue(any(["File sha256sum mismatch" in line for line in logger.output]))

            # Don't actually download, but make sure we would
            self.assertTrue(
                self.harness.charm.log_proxy._download_and_push_promtail_to_workload.called
            )

    @patch("ops.model.Container.pull")
    def test__promtail_can_handle_missing_configuration(self, mock_pull):
        mock_pull.side_effect = PathError(None, "irrelevant")
        self.assertEqual(self.harness.charm.log_proxy._current_config, {})


class TestLogProxyConsumerWithoutSyslog(unittest.TestCase):
    def setUp(self):

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
                for x in self.harness.charm.log_proxy._promtail_config["scrape_configs"]
            }
        )


class TestLogProxyConsumerWithPromtailResource(unittest.TestCase):
    def setUp(self):

        self.harness = Harness(
            ConsumerCharmWithPromtailResource, meta=ConsumerCharmWithPromtailResource.metadata_yaml
        )
        self.harness.set_model_info(name="MODEL", uuid="123456")
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

    def test__fetch_promtail_from_attached_resource(self):
        # "promtail-bin" is the resource name hardcoded in the lib
        self.assertFalse(self.harness.charm.log_proxy._promtail_attached_as_resource)

        self.harness.charm.model.resources._paths["promtail-bin"] = None
        self.harness.add_resource("promtail-bin", "somecontent")

        self.assertTrue(self.harness.charm.log_proxy._promtail_attached_as_resource)

        self.harness.set_can_connect("loki", True)
        with self.assertLogs(level="INFO") as logger:
            binary_path = os.path.join("/tmp", PROMTAIL_INFO["filename"])
            self.harness.charm.log_proxy._push_promtail_if_attached(binary_path)
            self.assertEqual(
                sorted(logger.output),
                [
                    "INFO:charms.loki_k8s.v0.loki_push_api:Promtail binary file has been obtained from an attached resource."
                ],
            )
