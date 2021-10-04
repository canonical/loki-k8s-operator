# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from typing import Dict
from unittest.mock import Mock, PropertyMock, patch

import yaml
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import LokiOperatorCharm
from loki_server import LokiServerError, LokiServerNotReadyError

LOKI_CONFIG = """
auth_enabled: false
chunk_store_config:
  max_look_back_period: 0s
compactor:
  shared_store: filesystem
  working_directory: /loki/boltdb-shipper-compactor
ingester:
  chunk_idle_period: 1h
  chunk_retain_period: 30s
  chunk_target_size: 1048576
  lifecycler:
    address: 127.0.0.1
    final_sleep: 0s
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  max_chunk_age: 1h
  max_transfer_retries: 0
limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h
ruler:
  alertmanager_url: ''
  enable_api: true
  ring:
    kvstore:
      store: inmemory
  rule_path: /loki/rules-temp
  storage:
    local:
      directory: /loki/rules
    type: local
schema_config:
  configs:
  - from: 2020-10-24
    index:
      period: 24h
      prefix: index_
    object_store: filesystem
    schema: v11
    store: boltdb-shipper
server:
  http_listen_port: 3100
storage_config:
  boltdb_shipper:
    active_index_directory: /loki/boltdb-shipper-active
    cache_location: /loki/boltdb-shipper-cache
    cache_ttl: 24h
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks
table_manager:
  retention_deletes_enabled: false
  retention_period: 0s
"""


class PushPullMock:
    def __init__(self):
        self._filesystem: Dict[str, str] = {}

    def pull(self, path: str, *args, **kwargs) -> str:
        return self._filesystem.get(path, "")

    def push(self, path: str, source: str, *args, **kwargs) -> None:
        self._filesystem[path] = source

    def patch_push(self):
        return patch("ops.testing._TestingPebbleClient.push", self.push)

    def patch_pull(self):
        return patch("ops.testing._TestingPebbleClient.pull", self.pull)


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name: str = "loki"
        self.push_pull_mock = PushPullMock()
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test__alerting_config(self):
        self.harness.charm.alertmanager_consumer = Mock()
        self.harness.charm.alertmanager_consumer.get_cluster_info.return_value = [
            "10.1.2.52",
            "10.1.3.52",
        ]
        expected_value = "http://10.1.2.52,http://10.1.3.52"
        self.assertEqual(self.harness.charm._alerting_config(), expected_value)

        self.harness.charm.alertmanager_consumer.get_cluster_info.return_value = []
        expected_value = ""
        self.assertEqual(self.harness.charm._alerting_config(), expected_value)

        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm._alerting_config()
            self.assertEqual(sorted(logger.output), ["DEBUG:charm:No alertmanagers available"])

    @patch("charm.LokiOperatorCharm._loki_config")
    def test__on_config_cannot_connect(self, mock_loki_config, *unused):
        self.harness.set_leader(True)
        mock_loki_config.return_value = yaml.safe_load(LOKI_CONFIG)
        self.harness.charm._container.can_connect = Mock()
        self.harness.charm._container.can_connect.return_value = False
        self.harness.update_config(yaml.safe_load(LOKI_CONFIG))
        self.assertIsInstance(self.harness.charm.unit.status, WaitingStatus)

    @patch("ops.testing._TestingPebbleClient.push")
    @patch("charm.LokiOperatorCharm._loki_config")
    def test__on_config_can_connect(self, mock_loki_config, *unused):
        self.harness.set_leader(True)
        mock_loki_config.return_value = yaml.safe_load(LOKI_CONFIG)
        self.harness.charm._container.can_connect = Mock()
        self.harness.charm._container.can_connect.return_value = True
        self.harness.update_config(yaml.safe_load(LOKI_CONFIG))
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test__provide_loki(self, mock_version):
        mock_version.return_value = "3.14159"

        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm._provide_loki()
            self.assertEqual(
                sorted(logger.output),
                ["DEBUG:charm:Loki Provider is available. Loki version: 3.14159"],
            )

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test__provide_loki_not_ready(self, mock_version):
        mock_version.side_effect = LokiServerNotReadyError
        self.harness.charm._provide_loki()
        self.assertIsInstance(self.harness.charm.unit.status, MaintenanceStatus)

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test__provide_loki_server_error(self, mock_version):
        mock_version.side_effect = LokiServerError
        self.harness.charm._provide_loki()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test__loki_config(self, mock_version):
        mock_version.return_value = "3.14159"

        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm._provide_loki()
            self.assertEqual(
                sorted(logger.output),
                ["DEBUG:charm:Loki Provider is available. Loki version: 3.14159"],
            )
