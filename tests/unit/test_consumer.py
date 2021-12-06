# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import textwrap
import unittest
from unittest.mock import PropertyMock, patch

from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer, _is_valid_rule
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness

LABELED_ALERT_RULES = [
    {
        "name": "loki_20ce8299-3634-4bef-8bd8-5ace6c8816b4_promtail-k8s_alerts",
        "rules": [
            {
                "alert": "HighPercentageError",
                "expr": 'sum(rate({juju_model="loki", juju_model_uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4", juju_application="promtail-k8s"} |= "error" [5m])) by (job)\n  /\nsum(rate({app="foo", env="production"}[5m])) by (job)\n  > 0.05\n',
                "for": "10m",
                "labels": {
                    "severity": "page",
                    "juju_model": "loki",
                    "juju_model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
                    "juju_application": "promtail-k8s",
                },
                "annotations": {"summary": "High request latency"},
            }
        ],
    }
]

ONE_RULE = {
    "alert": "HighPercentageError",
    "expr": 'sum(rate({%%juju_topology%%} |= "error" [5m])) by (job)\n  /\nsum(rate({app="foo", env="production"}[5m])) by (job)\n  > 0.05\n',
    "for": "10m",
    "labels": {"severity": "page"},
    "annotations": {"summary": "High request latency"},
}


class FakeConsumerCharm(CharmBase):
    _stored = StoredState()
    metadata_yaml = textwrap.dedent(
        """
        containers:
          promtail:
            resource: promtail-image

        requires:
          logging:
            interface: loki_push_api
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self.loki_consumer = LokiPushApiConsumer(self)

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP."""
        return "10.1.2.3"


class TestLokiPushApiConsumer(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeConsumerCharm, meta=FakeConsumerCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test__on_logging_relation_changed_no_leader(self):
        self.harness.set_leader(False)
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.assertEqual(self.harness.update_relation_data(rel_id, "promtail", {}), None)

    def test__on_logging_relation_changed_no_unit(self):
        self.harness.set_leader(True)
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.assertEqual(
            self.harness.update_relation_data(
                rel_id,
                "promtail",
                {"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
            ),
            None,
        )

    @patch(
        "charms.loki_k8s.v0.loki_push_api.load_alert_rules_from_dir",
        new_callable=PropertyMock,
    )
    def test__on_logging_relation_changed(self, mock_alert_rules):
        mock_alert_rules.return_value = (LABELED_ALERT_RULES, [])
        loki_push_api = "http://10.1.2.3:3100/loki/api/v1/push"
        self.harness.set_leader(True)
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.harness.update_relation_data(
            rel_id,
            "promtail",
            {"loki_push_api": '{"url": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        )

        self.assertEqual(
            self.harness.charm.loki_consumer._stored.loki_push_api.get(rel_id)["url"],
            loki_push_api,
        )
        self.assertEqual(self.harness.charm.loki_consumer.loki_push_api[0], {"url": loki_push_api})

    @patch("charms.loki_k8s.v0.loki_push_api.LoggingEvents.loki_push_api_endpoint_joined")
    def test__on_upgrade_charm_endpoint_joined_event_fired_for_leader(self, mock_events):
        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.harness.update_relation_data(
            rel_id,
            "promtail",
            {"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        )
        mock_events.emit.assert_called_once()

    @patch("charms.loki_k8s.v0.loki_push_api.LoggingEvents.loki_push_api_endpoint_joined")
    def test__on_upgrade_charm_endpoint_joined_event_fired_for_follower(self, mock_events):
        self.harness.set_leader(False)

        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.harness.update_relation_data(
            rel_id,
            "promtail",
            {"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        )
        mock_events.emit.assert_called_once()

    def test__label_alert_topology(self):
        labeled_alert_topology = self.harness.charm.loki_consumer._label_alert_topology(
            ONE_RULE.copy()
        )
        self.assertTrue("juju_model" in labeled_alert_topology["labels"])
        self.assertTrue("juju_model_uuid" in labeled_alert_topology["labels"])
        self.assertTrue("juju_application" in labeled_alert_topology["labels"])

    def test__is_valid_rule(self):
        self.assertTrue(_is_valid_rule(ONE_RULE.copy(), allow_free_standing=False))

        rule_1 = ONE_RULE.copy()
        del rule_1["alert"]
        self.assertFalse(_is_valid_rule(rule_1, allow_free_standing=False))

        rule_2 = ONE_RULE.copy()
        del rule_2["expr"]
        self.assertFalse(_is_valid_rule(rule_2, allow_free_standing=False))

        rule_3 = ONE_RULE.copy()
        rule_3["expr"] = "Missing Juju topology placeholder"
        self.assertFalse(_is_valid_rule(rule_3, allow_free_standing=False))
