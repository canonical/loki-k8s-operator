# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import unittest
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import hypothesis.strategies as st
import ops.testing
import yaml
from helpers import patch_network_get
from hypothesis import given
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
        self.harness.container_pebble_ready("loki")
        self.harness.charm._stored.config = LOKI_CONFIG

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


class TestPebblePlan(unittest.TestCase):
    """Feature: Multi-unit loki deployments.

    Background: TODO
    """

    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    @patch_network_get(private_address="1.1.1.1")
    @given(st.booleans(), st.integers(1, 3), st.integers(0, 3))
    def test_loki_starts_when_cluster_deployed_without_any_relations(
        self, is_leader, num_units, num_consumer_apps
    ):
        """Scenario: A loki cluster is deployed without any relations."""
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)

        # WHEN the unit is started as either a leader or not
        self.harness.set_leader(is_leader)

        # AND potentially some peers join
        self.peer_rel_id = self.harness.add_relation("replicas", self.harness.model.name)
        for i in range(1, num_units):
            self.harness.add_relation_unit(self.peer_rel_id, f"{self.harness.model.name}/{i}")
        self.assertEqual(self.harness.model.app.planned_units(), num_units)

        # AND potentially some logging relations join
        for i in range(num_consumer_apps):
            self.log_rel_id = self.harness.add_relation("logging", f"consumer-app-{i}")
            # Add two units per consumer app
            for u in range(2):
                self.harness.add_relation_unit(self.log_rel_id, f"consumer-app-{i}/{u}")

        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready("loki")

        # THEN a pebble service is created for this unit
        plan = self.harness.get_container_pebble_plan("loki")
        self.assertIn("loki", plan.services)

        # AND the command includes a config file
        command = plan.services["loki"].command
        self.assertIn("-config.file=", command)

        # AND the service is running
        container = self.harness.charm.unit.get_container("loki")
        service = container.get_service("loki")
        self.assertTrue(service.is_running())


class TestAppRelationData(unittest.TestCase):
    """Feature: Loki advertises common global info over app relation data.

    Background: Consumer charms need to have a URL for downloading promtail.
    """

    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    @patch_network_get(private_address="1.1.1.1")
    def setUp(self) -> None:
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)

        self.rel_id = self.harness.add_relation("logging", "consumer")
        self.harness.add_relation_unit(self.rel_id, "consumer/0")

        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready("loki")

    def test_endpoint(self):
        rel_data = self.harness.get_relation_data(self.rel_id, self.harness.charm.unit)
        # Relation data must include an "endpoints" key
        self.assertIn("endpoint", rel_data)
        endpoint = json.loads(rel_data["endpoint"])

        # The endpoint must be a dicts
        self.assertIsInstance(endpoint, dict)

        # Endpoint must have a "url" key
        self.assertIn("url", endpoint)
        self.assertTrue(endpoint["url"].startswith("http"))

    def test_promtail_url(self):
        rel_data = self.harness.get_relation_data(self.rel_id, self.harness.charm.app)

        # Relation data must include a "promtail_binary_zip_url" key
        self.assertIn("promtail_binary_zip_url", rel_data)

        # The value must be a url
        url = rel_data["promtail_binary_zip_url"]
        self.assertTrue(url.startswith("http"))
