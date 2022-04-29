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
from charm import LOKI_CONFIG as LOKI_CONFIG_PATH
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


class TestConfigFile(unittest.TestCase):
    """Feature: Loki config file in the workload container is rendered by the charm."""

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(LokiOperatorCharm)

        # GIVEN this unit is the leader
        self.harness.set_leader(True)

        # AND an "alerting" app joins with several units
        self.alerting_rel_id = self.harness.add_relation("alertmanager", "alertmanager-app")
        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready("loki")

    def test_relating_over_alertmanager_updates_config_with_ip_addresses(self):
        container = self.harness.charm.unit.get_container("loki")

        # WHEN no units are related over the alertmanager relation

        # THEN the `alertmanager_url` property is blank
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["ruler"]["alertmanager_url"], None)

        # WHEN alertmanager units join
        self.harness.add_relation_unit(self.alerting_rel_id, "alertmanager-app/0")
        self.harness.add_relation_unit(self.alerting_rel_id, "alertmanager-app/1")
        self.harness.update_relation_data(
            self.alerting_rel_id, "alertmanager-app/0", {"public_address": "10.0.0.1"}
        )
        self.harness.update_relation_data(
            self.alerting_rel_id, "alertmanager-app/1", {"public_address": "10.0.0.2"}
        )

        # THEN the `alertmanager_url` property has their ip addresses
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["ruler"]["alertmanager_url"], "http://10.0.0.1,http://10.0.0.2")

        # WHEN the relation is broken
        self.harness.remove_relation(self.alerting_rel_id)

        # THEN the `alertmanager_url` property is blank again
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["ruler"]["alertmanager_url"], None)

    def test_instance_address_is_set_to_this_unit_ip(self):
        container = self.harness.charm.unit.get_container("loki")
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))

        # TODO enable this assertion when the following is resolved
        # https://github.com/canonical/loki-k8s-operator/issues/159
        # self.assertEqual(config["common"]["ring"]["instance_addr"], "1.1.1.1")


class TestDelayedPebbleReady(unittest.TestCase):
    """Feature: Charm code must be resilient to any (reasonable) order of startup event firing."""

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        # Path _check_alert_rules, which attempts to talk to a loki server endpoint
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

    def test_pebble_ready_changes_status_from_waiting_to_active(self):
        """Scenario: a pebble-ready event is delayed."""
        # WHEN all startup hooks except pebble-ready finished

        # THEN app status is "Waiting" before pebble-ready
        self.assertIsInstance(self.harness.charm.unit.status, WaitingStatus)

        # AND app status is "Active" after pebble-ready
        self.harness.container_pebble_ready("loki")
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

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
