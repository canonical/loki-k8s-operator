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
        peers:
          loki-peers:
            interface: loki_peers
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
        self.ingress_per_unit = type(
            "IngressPerUnitRequirer",
            (object,),
            {
                "urls": None,
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

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.hostname}:{self.charm._port}/loki/api/v1/push"
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

    @property
    def external_url(self) -> str:
        """Return the external hostname to be passed to ingress via the relation."""
        return f"http://{self.hostname}:{self._port}"


class TestLokiPushApiProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeLokiCharm, meta=FakeLokiCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._generate_alert_rules_files",
        MagicMock(),
    )
    @patch(
        "charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._remove_alert_rules_files",
        MagicMock(),
    )
    @patch("urllib.request.urlopen")
    @patch("charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._endpoints")
    def test__on_logging_relation_changed(self, mock_endpoints, mock_urlopen):
        mock_urlopen.return_value = True
        with self.assertLogs(level="DEBUG") as logger:
            expected_data = [
                {"url": "http://loki0.endpoint/loki/api/v1/push"},
                {"url": "http://loki1.endpoint/loki/api/v1/push"},
            ]

            mock_endpoints.return_value = expected_data
            rel_id = self.harness.add_relation("logging", "promtail")
            self.harness.add_relation_unit(rel_id, "promtail/0")
            self.harness.update_relation_data(rel_id, "promtail", {"alert_rules": "ww"})
            data = self.harness.get_relation_data(rel_id, self.harness.model.app.name)

            self.assertTrue("endpoints" in data)
            self.assertTrue(json.dumps(expected_data[0]) in data["endpoints"])
            self.assertTrue(json.dumps(expected_data[1]) in data["endpoints"])

            self.assertEqual(
                logger.output[1],
                "DEBUG:charms.loki_k8s.v0.loki_push_api:Saved alerts rules to disk",
            )
            self.assertEqual(
                logger.output[2], "DEBUG:charms.loki_k8s.v0.loki_push_api:Checking alert rules: Ok"
            )

    @patch("os.makedirs", MagicMock())
    @patch("urllib.request.urlopen")
    @patch("charms.loki_k8s.v0.loki_push_api.LokiPushApiProvider._endpoints")
    def test_alerts(self, mock_endpoints, mock_urlopen):
        mock_urlopen.return_value = True
        expected_data = [
            {"url": "http://loki0.endpoint/loki/api/v1/push"},
            {"url": "http://loki1.endpoint/loki/api/v1/push"},
        ]

        mock_endpoints.return_value = expected_data
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
            msg = "no rule groups found"
            mock_urlopen.side_effect = HTTPError(URL, 404, msg, {}, io.BytesIO(msg.encode()))  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.assertTrue(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_404_error(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            msg = "404 page not found"
            mock_urlopen.side_effect = HTTPError(URL, 404, msg, {}, io.BytesIO(msg.encode()))  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.assertFalse(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_httperror_400(self, mock_urlopen):
        with patch("http.client.HTTPResponse") as mock_http_response:
            msg = "Bad Request"
            mock_urlopen.side_effect = HTTPError(URL, 400, msg, {}, io.BytesIO(msg.encode()))  # type: ignore
            mock_http_response.read.return_value = mock_urlopen.side_effect
            self.assertFalse(self.harness.charm.loki_provider._check_alert_rules())

    @patch("urllib.request.urlopen")
    def test__check_alert_rules_urlerror(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Unknown host")
        # mock_http_response.read.return_value = mock_urlopen.side_effect
        self.assertFalse(self.harness.charm.loki_provider._check_alert_rules())
