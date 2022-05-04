# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import io
import json
import textwrap
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

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
        self._port = 3100
        self._container = type(
            "FakeContainer",
            (object,),
            {
                "make_dir": lambda *a, **kw: None,
                "push": lambda *a, **kw: None,
                "remove_path": lambda *a, **kw: None,
                "can_connect": lambda *a, **kw: True,
                "list_files": lambda *a, **kw: [],
            },
        )
        with patch("ops.testing._TestingPebbleClient.make_dir"):
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
        self._stored.events.append({"message": event.message, "error": event.error})

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
        self.harness.begin()

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
        with self.assertLogs(level="DEBUG") as logger:
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
            self.assertTrue(
                any(
                    [
                        log_msg
                        == "DEBUG:charms.loki_k8s.v0.loki_push_api:Saved alert rules to disk"
                        for log_msg in logger.output
                    ]
                )
            )

    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._generate_alert_rules_files",
        MagicMock(),
    )
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._remove_alert_rules_files",
        MagicMock(),
    )
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._regenerate_alert_rules",
        MagicMock(),
    )
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
        self.assertEqual(self.harness.charm.loki_provider._regenerate_alert_rules.call_count, 1)

        self.harness.remove_relation(rel_id)
        # This will be called once on depart and once on broken
        # awaiting a cull of the mocking to look at the actual container
        self.assertEqual(self.harness.charm.loki_provider._regenerate_alert_rules.call_count, 3)

    @patch("os.makedirs", MagicMock())
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

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_ok(self, mock_urlopen):
        mock_urlopen.return_value = True
        self.harness.charm.loki_provider._check_alert_rules()
        self.assertEqual(self.harness.charm._stored.events[-1]["error"], False)

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_404_ok(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            mock_http_response.read.side_effect = HTTPError(URL, 404, "no rule groups found", {}, io.BytesIO())  # type: ignore
            mock_urlopen.return_value = mock_http_response
            self.harness.charm.loki_provider._check_alert_rules()
            self.assertEqual(self.harness.charm._stored.events[-1]["error"], False)

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_404_error(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            mock_urlopen.side_effect = HTTPError(URL, 404, "404 page not found", {}, io.BytesIO())  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.harness.charm.loki_provider._check_alert_rules()
            self.assertEqual(self.harness.charm._stored.events[-1]["error"], True)

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_400(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            mock_urlopen.side_effect = HTTPError(URL, 400, "Bad Request", {}, io.BytesIO())  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.harness.charm.loki_provider._check_alert_rules()
            self.assertEqual(self.harness.charm._stored.events[-1]["error"], True)

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_urlerror(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Unknown host")
        self.harness.charm.loki_provider._check_alert_rules()
        self.assertEqual(self.harness.charm._stored.events[-1]["error"], True)
