# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import textwrap
import unittest
from unittest.mock import patch

from charms.loki_k8s.v0.loki_push_api import LokiPushApiProvider
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness

METADATA = {
    "model": "consumer-model",
    "model_uuid": "qwerty-1234",
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

URL = "http://127.0.0.1:3100/loki/api/v1/rules"


class FakeLokiCharm(CharmBase):
    _stored = StoredState()
    metadata_yaml = textwrap.dedent(
        """
        containers:
          loki:
            resource: loki-image
            mounts:
              - storage: active-index-directory
                location: /loki/boltdb-shipper-active
              - storage: loki-chunks
                location: /loki/chunks

        provides:
          logging:
            interface: loki_push_api
          grafana-source:
            interface: grafana_datasource
            optional: true

        requires:
          alertmanager:
            interface: alertmanager_dispatch
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._container = self.unit.get_container("loki")
        self._port = 3100
        self.loki_provider = LokiPushApiProvider(
            self,
            address="10.0.0.1",
            port=3100,
            scheme="http",
            path="/loki/api/v1/push",
        )

        self.framework.observe(
            self.loki_provider.on.loki_push_api_alert_rules_changed, self.alert_events
        )
        self._stored.set_default(events=[])

    def alert_events(self, event):
        self._stored.events.append({"relation": event.relation})

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def hostname(self) -> str:
        """Unit's hostname."""
        return "{}-{}.{}-endpoints.{}.svc.cluster.local".format(
            self.app.name,
            self.unit.name.split("/")[-1],
            self.app.name,
            self.model.name,
        )


class TestLokiPushApiProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeLokiCharm, meta=FakeLokiCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

    def test_relation_data(self):
        self.harness.charm.app.name = "loki"
        base_url = "http://loki-0.loki-endpoints.None.svc.cluster.local"
        port = "3100"
        url = "{}:{}".format(base_url, port)
        path = "/loki/api/v1/push"
        endpoint = "{}{}".format(url, path)
        expected_value = {"url": endpoint}
        self.assertEqual(expected_value, self.harness.charm.loki_provider._endpoint(url))

    @patch("ops.testing._TestingModelBackend.network_get")
    def test__on_logging_relation_changed(self, mock_unit_ip):
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [{"hostname": "loki-0", "value": "10.1.2.3"}],
                }
            ]
        }
        mock_unit_ip.return_value = fake_network
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")

        self.harness.update_relation_data(
            rel_id, "promtail", {"alert_rules": json.dumps(ALERT_RULES)}
        )
        self.assertEqual(len(self.harness.charm._stored.events), 1)

    @patch("ops.testing._TestingModelBackend.network_get")
    def test__on_logging_relation_created_and_broken(self, mock_unit_ip):
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [{"hostname": "loki-0", "value": "10.1.2.3"}],
                }
            ]
        }
        mock_unit_ip.return_value = fake_network
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")

        self.harness.update_relation_data(
            rel_id, "promtail", {"alert_rules": json.dumps(ALERT_RULES)}
        )
        self.assertEqual(len(self.harness.charm._stored.events), 1)

        self.harness.remove_relation(rel_id)
        self.assertEqual(len(self.harness.charm._stored.events), 3)

    @patch("ops.testing._TestingModelBackend.network_get")
    def test_alerts(self, mock_unit_ip):
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [{"hostname": "loki-0", "value": "10.1.2.3"}],
                }
            ]
        }
        mock_unit_ip.return_value = fake_network
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

        alerts = self.harness.charm.loki_provider.alerts
        self.assertEqual(len(alerts), 1)
        self.assertDictEqual(list(alerts.values())[0]["groups"][0], ALERT_RULES["groups"][0])
