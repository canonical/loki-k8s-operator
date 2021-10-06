# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest
from unittest.mock import PropertyMock, patch

from charms.loki_k8s.v0.loki_push_api import LokiProvider
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness

METADATA = {
    "model": "consumer-model",
    "model_uuid": "qwerty-1234",
    "application": "promtail",
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


class FakeLokiCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self.loki_provider = LokiProvider(self, "logging")

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP"""
        return "10.1.2.3"


class TestLokiProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeLokiCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    @patch("charms.loki_k8s.v0.loki_push_api.LokiProvider.unit_ip", new_callable=PropertyMock)
    def test_relation_data(self, mock_unit_ip):
        mock_unit_ip.return_value = "10.1.2.3"
        expected_value = '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'
        self.assertEqual(expected_value, self.harness.charm.loki_provider._loki_push_api)

    @patch("charms.loki_k8s.v0.loki_push_api.LokiProvider._generate_alert_rules_files")
    @patch("charms.loki_k8s.v0.loki_push_api.LokiProvider._remove_alert_rules_files")
    @patch("charms.loki_k8s.v0.loki_push_api.LokiProvider.unit_ip", new_callable=PropertyMock)
    def test__on_logging_relation_changed(self, mock_unit_ip, *unused):
        with self.assertLogs(level="DEBUG") as logger:
            mock_unit_ip.return_value = "10.1.2.3"
            rel_id = self.harness.add_relation("logging", "promtail")
            self.harness.add_relation_unit(rel_id, "promtail/0")
            self.harness.update_relation_data(rel_id, "promtail/0", {})
            self.assertEqual(
                sorted(logger.output)[0],
                'DEBUG:charms.loki_k8s.v0.loki_push_api:Saving Loki url in relation data {"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}',
            )

            self.harness.update_relation_data(rel_id, "promtail", {"alert_rules": "ww"})
            self.assertEqual(
                sorted(logger.output)[1],
                "DEBUG:charms.loki_k8s.v0.loki_push_api:Saving alerts rules to disk",
            )

    @patch("os.makedirs")
    @patch("ops.testing._TestingPebbleClient.remove_path")
    @patch("charms.loki_k8s.v0.loki_push_api.LokiProvider.unit_ip", new_callable=PropertyMock)
    def test_alerts(self, mock_unit_ip, *unused):
        mock_unit_ip.return_value = "10.1.2.3"
        rel_id = self.harness.add_relation("logging", "consumer")
        self.harness.update_relation_data(
            rel_id,
            "consumer",
            {
                "metadata": json.dumps(METADATA),
                "alert_rules": json.dumps(ALERT_RULES),
            },
        )
        self.harness.add_relation_unit(rel_id, "consumer/0")
        alerts = self.harness.charm.loki_provider.alerts()
        self.assertEqual(len(alerts), 1)
        self.assertDictEqual(alerts[0]["groups"][0], ALERT_RULES["groups"][0])
