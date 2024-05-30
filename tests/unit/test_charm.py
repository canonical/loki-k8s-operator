# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import os
import unittest
from io import BytesIO
from unittest.mock import Mock, PropertyMock, patch
from urllib.error import HTTPError, URLError

import yaml
from charm import LOKI_CONFIG as LOKI_CONFIG_PATH
from charm import LokiOperatorCharm
from helpers import FakeProcessVersionCheck, k8s_resource_multipatch
from ops.model import ActiveStatus, BlockedStatus, Container, MaintenanceStatus
from ops.testing import Harness

METADATA = {
    "model": "consumer-model",
    "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
    "application": "promtail",
    "charm_name": "charm-k8s",
}

ALERT_RULES = {
    "groups": [
        {
            "name": "None_f2c1b2a6-e006-11eb-ba80-0242ac130004_consumer-tester_alerts",
            "rules": [
                {
                    "alert": "HighPercentageError",
                    "expr": "sum(rate({%%juju_topology%%} |= 'error' [5m])) by (job)",
                    "for": "0m",
                    "labels": {
                        "severity": "Low",
                    },
                    "annotations": {
                        "summary": "High request latency",
                    },
                },
            ],
        }
    ]
}

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
    @k8s_resource_multipatch
    @patch("lightkube.core.client.GenericSyncClient")
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def setUp(self, *_):
        self.container_name: str = "loki"
        version_patcher = patch(
            "charm.LokiOperatorCharm._loki_version",
            new_callable=PropertyMock,
            return_value="3.14159",
        )
        os.environ["JUJU_VERSION"] = "3.0.3"
        self.mock_version = version_patcher.start()
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.addCleanup(version_patcher.stop)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready("loki")

    def test__alerting_config(self):
        self.harness.charm.alertmanager_consumer = Mock()
        mock_cluster = {"http://10.1.2.52", "http://10.1.3.52"}
        self.harness.charm.alertmanager_consumer.get_cluster_info.return_value = mock_cluster
        expected_value = "http://10.1.2.52,http://10.1.3.52"
        self.assertEqual(mock_cluster, set(self.harness.charm._alerting_config().split(",")))

        self.harness.charm.alertmanager_consumer.get_cluster_info.return_value = set()
        expected_value = ""
        self.assertEqual(self.harness.charm._alerting_config(), expected_value)

        with self.assertLogs(level="DEBUG") as logger:
            self.harness.charm._alerting_config()
            searched_message = "DEBUG:charm:No alertmanagers available"
            any_matches = any(searched_message in log_message for log_message in logger.output)
            self.assertTrue(any_matches)

    @patch("config_builder.ConfigBuilder.build")
    @k8s_resource_multipatch
    def test__on_config_cannot_connect(self, mock_loki_config):
        self.harness.set_leader(True)
        self.harness.set_can_connect("loki", False)
        mock_loki_config.return_value = yaml.safe_load(LOKI_CONFIG)

        # Since harness was not started with begin_with_initial_hooks(), this must
        # be emitted by hand to actually trigger _configure()
        self.harness.charm.on.config_changed.emit()
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, MaintenanceStatus)

    @patch("config_builder.ConfigBuilder.build")
    @k8s_resource_multipatch
    def test__on_config_can_connect(self, mock_loki_config):
        mock_loki_config.return_value = yaml.safe_load(LOKI_CONFIG)
        self.harness.set_leader(True)

        # Since harness was not started with begin_with_initial_hooks(), this must
        # be emitted by hand to actually trigger _configure()
        self.harness.charm.on.config_changed.emit()
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)


class TestConfigFile(unittest.TestCase):
    """Feature: Loki config file in the workload container is rendered by the charm."""

    @patch("socket.getfqdn", new=lambda *args: "fqdn")
    @k8s_resource_multipatch
    @patch("lightkube.core.client.GenericSyncClient")
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def setUp(self, *_):
        os.environ["JUJU_VERSION"] = "3.0.3"
        # Patch _check_alert_rules, which attempts to talk to a loki server endpoint
        self.check_alert_rules_patcher = patch(
            "charm.LokiOperatorCharm._check_alert_rules",
            new=lambda x: True,
        )
        self.check_alert_rules_patcher.start()

        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)

        # GIVEN this unit is the leader
        self.harness.set_leader(True)

        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready("loki")

    def tearDown(self):
        self.check_alert_rules_patcher.stop()

    @k8s_resource_multipatch
    def test_relating_over_alertmanager_updates_config_with_ip_addresses(self):
        """Scenario: The charm is related to alertmanager."""
        container = self.harness.charm.unit.get_container("loki")

        # WHEN no units are related over the alertmanager relation

        # THEN the `alertmanager_url` property is blank (`yaml.safe_load` converts blanks to None)
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["ruler"]["alertmanager_url"], "")

        # WHEN alertmanager units join
        self.alerting_rel_id = self.harness.add_relation("alertmanager", "alertmanager-app")
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
        self.assertEqual(
            set(config["ruler"]["alertmanager_url"].split(",")),
            {"http://10.0.0.1", "http://10.0.0.2"},
        )

        # WHEN the relation is broken
        self.harness.remove_relation(self.alerting_rel_id)

        # THEN the `alertmanager_url` property is blank again
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["ruler"]["alertmanager_url"], "")

    @patch("socket.getfqdn", new=lambda *args: "fqdn")
    def test_instance_address_is_set_to_this_unit_ip(self):
        container = self.harness.charm.unit.get_container("loki")

        # WHEN no units are related over the logging relation

        # THEN the `instance_addr` property has the fqdn
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["common"]["ring"]["instance_addr"], "fqdn")

        # WHEN logging units join
        self.log_rel_id = self.harness.add_relation("logging", "logging-app")
        self.harness.add_relation_unit(self.log_rel_id, "logging-app/0")
        self.harness.add_relation_unit(self.log_rel_id, "logging-app/1")
        self.harness.update_relation_data(
            self.log_rel_id, "logging-app/0", {"something": "just to trigger rel-changed event"}
        )

        self.harness.charm.on.config_changed.emit()

        # THEN the `instance_addr` property has the fqdn
        config = yaml.safe_load(container.pull(LOKI_CONFIG_PATH))
        self.assertEqual(config["common"]["ring"]["instance_addr"], "fqdn")


class TestPebblePlan(unittest.TestCase):
    """Feature: Multi-unit loki deployments.

    Background: TODO
    """

    @k8s_resource_multipatch
    @patch("lightkube.core.client.GenericSyncClient")
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def test_loki_starts_when_cluster_deployed_without_any_relations(self, *_):
        """Scenario: A loki cluster is deployed without any relations."""
        is_leader = True
        num_consumer_apps = 3
        os.environ["JUJU_VERSION"] = "3.0.3"
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)

        # WHEN the unit is started as either a leader or not
        self.harness.set_leader(is_leader)

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


class TestDelayedPebbleReady(unittest.TestCase):
    """Feature: Charm code must be resilient to any (reasonable) order of startup event firing."""

    @k8s_resource_multipatch
    @patch("lightkube.core.client.GenericSyncClient")
    def setUp(self, *_):
        os.environ["JUJU_VERSION"] = "3.0.3"
        # Patch _check_alert_rules, which attempts to talk to a loki server endpoint
        self.check_alert_rules_patcher = patch(
            "charm.LokiOperatorCharm._check_alert_rules",
            new=lambda x: True,
        )
        self.check_alert_rules_patcher.start()
        self.version_patcher = patch(
            "charm.LokiOperatorCharm._loki_version",
            new_callable=PropertyMock,
            return_value="3.14159",
        )
        self.version_patcher.start()
        self.harness = Harness(LokiOperatorCharm)

        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()
        self.harness.charm.on.config_changed.emit()

        # AND a "logging" app joins with several units
        self.log_rel_id = self.harness.add_relation("logging", "consumer-app")
        self.harness.add_relation_unit(self.log_rel_id, "consumer-app/0")
        self.harness.add_relation_unit(self.log_rel_id, "consumer-app/1")
        self.harness.update_relation_data(
            self.log_rel_id,
            "consumer-app",
            {
                "metadata": "{}",
                "alert_rules": "{}",
            },
        )

    def tearDown(self):
        self.check_alert_rules_patcher.stop()
        self.version_patcher.stop()

    @k8s_resource_multipatch
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def test_pebble_ready_changes_status_from_waiting_to_active(self):
        """Scenario: a pebble-ready event is delayed."""
        # WHEN all startup hooks except pebble-ready finished
        # THEN app status is "Maintenance" before pebble-ready
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, MaintenanceStatus)

        # AND app status is "Active" after pebble-ready
        self.harness.container_pebble_ready("loki")
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

    @k8s_resource_multipatch
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def test_regular_relation_departed_runs_before_pebble_ready(self):
        """Scenario: a regular relation is removed quickly, before pebble-ready fires."""
        # WHEN relation-departed fires before pebble-ready
        self.harness.remove_relation_unit(self.log_rel_id, "consumer-app/1")

        # THEN app status is "Waiting" before pebble-ready
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, MaintenanceStatus)

        # AND app status is "Active" after pebble-ready
        self.harness.container_pebble_ready("loki")
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

    @k8s_resource_multipatch
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def test_regular_relation_broken_runs_before_pebble_ready(self):
        """Scenario: a regular relation is removed quickly, before pebble-ready fires."""
        # WHEN relation-broken fires before pebble-ready
        self.harness.remove_relation(self.log_rel_id)

        # THEN app status is "Waiting" before pebble-ready
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, MaintenanceStatus)

        # AND app status is "Active" after pebble-ready
        self.harness.container_pebble_ready("loki")
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)


class TestAppRelationData(unittest.TestCase):
    """Feature: Loki advertises common global info over app relation data.

    Background: Consumer charms need to have a URL for downloading promtail.
    """

    @k8s_resource_multipatch
    @patch("lightkube.core.client.GenericSyncClient")
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def setUp(self, *_) -> None:
        os.environ["JUJU_VERSION"] = "3.0.3"
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
        promtail_binaries = json.loads(rel_data["promtail_binary_zip_url"])
        url = promtail_binaries["amd64"]["url"]
        self.assertTrue(url.startswith("http"))


class TestAlertRuleBlockedStatus(unittest.TestCase):
    """Ensure that Loki 'keeps' BlockedStatus from alert rules until another rules event."""

    @k8s_resource_multipatch
    @patch("lightkube.core.client.GenericSyncClient")
    @patch.object(Container, "exec", new=FakeProcessVersionCheck)
    def setUp(self, *_):
        os.environ["JUJU_VERSION"] = "3.0.3"
        # Patch _check_alert_rules, which attempts to talk to a loki server endpoint
        self.patcher = patch("urllib.request.urlopen", new=Mock())
        self.mock_request = self.patcher.start()
        self.addCleanup(self.mock_request.stop)

        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()
        self.harness.container_pebble_ready("loki")

    def tearDown(self):
        self.mock_request.stop()

    @patch("ops.testing._TestingModelBackend.network_get")
    def _add_alerting_relation(self, mock_unit_ip):
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [{"hostname": "loki-0", "value": "10.1.2.3"}],
                }
            ]
        }
        mock_unit_ip.return_value = fake_network
        rel_id = self.harness.add_relation("logging", "tester")
        self.harness.add_relation_unit(rel_id, "tester/0")

        self.harness.update_relation_data(
            rel_id,
            "tester",
            {"metadata": json.dumps(METADATA), "alert_rules": json.dumps(ALERT_RULES)},
        )

    @k8s_resource_multipatch
    def test__alert_rule_errors_appropriately_set_state(self):
        self.harness.charm.on.config_changed.emit()
        self.mock_request.side_effect = HTTPError(
            url="http://example.com",
            code=404,
            msg="fubar!",
            fp=BytesIO(initial_bytes="fubar!".encode()),
            hdrs=None,  # type: ignore
        )
        self._add_alerting_relation()
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

        # Emit another config changed to make sure we stay blocked
        self.harness.charm.on.config_changed.emit()
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

        self.mock_request.side_effect = None
        self.mock_request.return_value = BytesIO(initial_bytes="success".encode())

        self.harness.charm._loki_push_api_alert_rules_changed(None)
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)

    @k8s_resource_multipatch
    def test__loki_connection_errors_on_lifecycle_events_appropriately_clear(self):
        self.harness.charm.on.config_changed.emit()
        self.mock_request.side_effect = URLError(reason="fubar!")
        self._add_alerting_relation()
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

        # Emit another config changed to make sure we unblock
        self.mock_request.side_effect = None
        self.mock_request.return_value = BytesIO(initial_bytes="success".encode())
        self.harness.charm.on.config_changed.emit()
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, ActiveStatus)
