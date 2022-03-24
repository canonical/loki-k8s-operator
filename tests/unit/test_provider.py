# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import io
import json
import textwrap
import unittest
from unittest.mock import MagicMock, PropertyMock, patch
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
                "remove_path": lambda *a, **kw: None,
                "can_connect": lambda *a, **kw: True,
                "list_files": lambda *a, **kw: [],
            },
        )
        with patch("ops.testing._TestingPebbleClient.make_dir"):
            self.loki_provider = LokiPushApiProvider(
                self,
                endpoint_address="10.0.0.1",
                endpoint_port=3100,
                endpoint_schema="http",
                endpoint_path="/loki/api/v1/push",
            )

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP."""
        return "10.1.2.3"


class TestLokiPushApiProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeLokiCharm, meta=FakeLokiCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test_relation_data(self):
        self.harness.charm.app.name = "loki"
        expected_value = [
            {"url": "http://loki-0.loki-endpoints.None.svc.cluster.local:3100/loki/api/v1/push"}
        ]
        self.assertEqual(expected_value, self.harness.charm.loki_provider._endpoints())

    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._generate_alert_rules_files",
        MagicMock(),
    )
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._remove_alert_rules_files",
        MagicMock(),
    )
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider.unit_ip", new_callable=PropertyMock
    )
    def test__on_logging_relation_changed(self, mock_unit_ip):
        with self.assertLogs(level="DEBUG") as logger:
            mock_unit_ip.return_value = "10.1.2.3"
            rel_id = self.harness.add_relation("logging", "promtail")
            self.harness.add_relation_unit(rel_id, "promtail/0")

            self.harness.update_relation_data(rel_id, "promtail", {"alert_rules": "ww"})
            self.assertEqual(
                sorted(logger.output)[0],
                "DEBUG:charms.loki_k8s.v0.loki_push_api:Saved alerts rules to disk",
            )

    @patch("os.makedirs", MagicMock())
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider.unit_ip", new_callable=PropertyMock
    )
    def test_alerts(self, mock_unit_ip):
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
        self.assertDictEqual(list(alerts.values())[0]["groups"][0], ALERT_RULES["groups"][0])

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_ok(self, mock_urlopen):
        mock_urlopen.return_value = True
        self.assertTrue(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_404_ok(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            mock_http_response.read.side_effect = HTTPError(URL, 404, "no rule groups found", {}, io.BytesIO())  # type: ignore
            mock_urlopen.return_value = mock_http_response
            self.assertTrue(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_404_error(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            mock_urlopen.side_effect = HTTPError(URL, 404, "404 page not found", {}, io.BytesIO())  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.assertFalse(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_400(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            mock_urlopen.side_effect = HTTPError(URL, 400, "Bad Request", {}, io.BytesIO())  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.assertFalse(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_urlerror(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Unknown host")
        self.assertFalse(self.harness.charm.loki_provider._check_alert_rules())
