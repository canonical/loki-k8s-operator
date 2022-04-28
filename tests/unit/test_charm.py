# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import ops
import yaml
from helpers import patch_network_get, tautology
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import LokiOperatorCharm
from loki_server import LokiServerError, LokiServerNotReadyError

ops.testing.SIMULATE_CAN_CONNECT = True

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


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.container_name: str = "loki"
        version_patcher = patch(
            "loki_server.LokiServer.version", new_callable=PropertyMock, return_value="3.14159"
        )
        self.mock_version = version_patcher.start()
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.addCleanup(version_patcher.stop)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()
        self.harness.charm._stored.config = LOKI_CONFIG
        self.harness.container_pebble_ready("loki")

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

    @patch("ops.model.Container.can_connect", MagicMock(return_value=False))
    @patch("charm.LokiOperatorCharm._loki_config")
    def test__on_config_cannot_connect(self, mock_loki_config):
        self.harness.set_leader(True)
        mock_loki_config.return_value = yaml.safe_load(LOKI_CONFIG)

        # Since harness was not started with begin_with_initial_hooks(), this must
        # be emitted by hand to actually trigger _configure()
        self.harness.charm.on.config_changed.emit()
        self.assertIsInstance(self.harness.charm.unit.status, WaitingStatus)

    @patch("charm.LokiOperatorCharm._loki_config")
    def test__on_config_can_connect(self, mock_loki_config):
        mock_loki_config.return_value = yaml.safe_load(LOKI_CONFIG)
        self.harness.set_leader(True)

        # Since harness was not started with begin_with_initial_hooks(), this must
        # be emitted by hand to actually trigger _configure()
        self.harness.charm.on.config_changed.emit()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

    def test__provide_loki(self):
        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm._provide_loki()
            self.assertEqual(
                sorted(logger.output),
                ["DEBUG:charm:Loki Provider is available. Loki version: 3.14159"],
            )

    def test__provide_loki_not_ready(self):
        self.mock_version.side_effect = LokiServerNotReadyError
        self.harness.charm._provide_loki()
        self.assertIsInstance(self.harness.charm.unit.status, WaitingStatus)

    def test__provide_loki_server_error(self):
        self.mock_version.side_effect = LokiServerError
        self.harness.charm._provide_loki()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test__loki_config(self):
        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm._provide_loki()
            self.assertEqual(
                sorted(logger.output),
                ["DEBUG:charm:Loki Provider is available. Loki version: 3.14159"],
            )


class TestDelayedPebbleReady(unittest.TestCase):
    """Feature: Charm code must be resilient to any (reasonable) order of startup event firing."""

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.check_alert_rules_patcher = patch(
            "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._check_alert_rules",
            new=tautology,
        )
        self.check_alert_rules_patcher.start()
        self.harness = Harness(LokiOperatorCharm)

        # GIVEN this unit is the leader
        self.harness.set_leader(True)

        # AND a "logging" app joins with several units
        self.log_rel_id = self.harness.add_relation("logging", "consumer-app")
        self.harness.add_relation_unit(self.log_rel_id, "consumer-app/0")
        self.harness.add_relation_unit(self.log_rel_id, "consumer-app/1")
        self.harness.begin_with_initial_hooks()
        # self.harness.charm.loki_provider._check_alert_rules = tautology
        self.harness.update_relation_data(
            self.log_rel_id,
            "consumer-app",
            {
                "metadata": {},
                "alert_rules": {},
            },
        )

    def tearDown(self):
        self.check_alert_rules_patcher.stop()

    def test_regular_relation_departed_runs_before_pebble_ready(self):
        """Scenario: a regular relation is removed quickly, before pebble-ready fires."""
        # WHEN relation-departed fires before pebble-ready
        self.harness.remove_relation_unit(self.log_rel_id, "consumer-app/1")

        # THEN app status is "Waiting" before pebble-ready
        self.assertIsInstance(self.harness.charm.unit.status, WaitingStatus)

        # AND app status is "Active" after pebble-ready
        self.harness.container_pebble_ready("loki")
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

    def test_regular_relation_broken_runs_before_pebble_ready(self):
        """Scenario: a regular relation is removed quickly, before pebble-ready fires."""
        # WHEN relation-broken fires before pebble-ready
        self.harness.remove_relation(self.log_rel_id)

        # THEN app status is "Waiting" before pebble-ready
        self.assertIsInstance(self.harness.charm.unit.status, WaitingStatus)

        # AND app status is "Active" after pebble-ready
        self.harness.container_pebble_ready("loki")
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)
