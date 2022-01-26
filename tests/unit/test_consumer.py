# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
import textwrap
import unittest
from unittest.mock import patch

import yaml
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer, _is_valid_rule
from helpers import TempFolderSandbox
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

    @patch("charms.loki_k8s.v0.loki_push_api.AlertRules.add_path")
    @patch("charms.loki_k8s.v0.loki_push_api.AlertRules.as_dict", new=lambda *a, **kw: {})
    def test__on_logging_relation_changed(self, mock_as_dict):
        mock_as_dict.return_value = (LABELED_ALERT_RULES, {})
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

    @patch("charms.loki_k8s.v0.loki_push_api.LokiPushApiEvents.loki_push_api_endpoint_joined")
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

    @patch("charms.loki_k8s.v0.loki_push_api.LokiPushApiEvents.loki_push_api_endpoint_joined")
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


class TestReloadAlertRules(unittest.TestCase):
    """Feature: Consumer charm can manually invoke reloading of alerts.

    Background: In use cases such as cos-configuration-k8s-operator, the last hook can fire before
    the alert files show up on disk. In that case relation data would remain empty of alerts. To
    circumvent that, a public method for reloading alert rules is offered.
    """

    NO_ALERTS = json.dumps({})  # relation data representation for the case of "no alerts"

    # use a short-form free-standing alert, for brevity
    ALERT = yaml.safe_dump({"alert": "free_standing", "expr": "avg(some_vector[5m]) > 5"})

    def setUp(self):
        self.sandbox = TempFolderSandbox()
        alert_rules_path = os.path.join(self.sandbox.root, "alerts")
        self.alert_rules_path = alert_rules_path

        class ConsumerCharm(CharmBase):
            metadata_yaml = textwrap.dedent(
                """
                requires:
                  logging:
                    interface: loki_push_api
                """
            )

            def __init__(self, *args, **kwargs):
                super().__init__(*args)
                self._port = 3100
                self.loki_consumer = LokiPushApiConsumer(
                    self, alert_rules_path=alert_rules_path, recursive=True
                )

        self.harness = Harness(ConsumerCharm, meta=ConsumerCharm.metadata_yaml)
        # self.harness = Harness(FakeConsumerCharm, meta=FakeConsumerCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()
        self.harness.set_leader(True)
        self.rel_id = self.harness.add_relation("logging", "loki")

        # need to manually emit relation changed
        # https://github.com/canonical/operator/issues/682
        self.harness.charm.on.logging_relation_changed.emit(
            self.harness.charm.model.get_relation("logging")
        )

    def test_reload_when_dir_is_still_empty_changes_nothing(self):
        """Scenario: The reload method is called when the alerts dir is still empty."""
        # GIVEN relation data contains no alerts
        relation = self.harness.charm.model.get_relation("logging")
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

        # WHEN no rule files are present

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is unchanged
        relation = self.harness.charm.model.get_relation("logging")
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

    def test_reload_after_dir_is_populated_updates_relation_data(self):
        """Scenario: The reload method is called after some alert files are added."""
        # GIVEN relation data contains no alerts
        relation = self.harness.charm.model.get_relation("logging")
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

        # WHEN some rule files are added to the alerts dir
        self.sandbox.put_file(os.path.join(self.alert_rules_path, "alert.rule"), self.ALERT)

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is updated
        relation = self.harness.charm.model.get_relation("logging")
        self.assertNotEqual(
            relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS
        )

    def test_reload_after_dir_is_emptied_updates_relation_data(self):
        """Scenario: The reload method is called after all the loaded alert files are removed."""
        # GIVEN alert files are present and relation data contains respective alerts
        alert_filename = os.path.join(self.alert_rules_path, "alert.rule")
        self.sandbox.put_file(alert_filename, self.ALERT)
        self.harness.charm.loki_consumer._reinitialize_alert_rules()
        relation = self.harness.charm.model.get_relation("logging")
        self.assertNotEqual(
            relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS
        )

        # WHEN all rule files are deleted from the alerts dir
        self.sandbox.remove(alert_filename)

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is empty again
        relation = self.harness.charm.model.get_relation("logging")
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

    def test_reload_after_dir_itself_removed_updates_relation_data(self):
        """Scenario: The reload method is called after the alerts dir doesn't exist anymore."""
        # GIVEN alert files are present and relation data contains respective alerts
        alert_filename = os.path.join(self.alert_rules_path, "alert.rule")
        self.sandbox.put_file(alert_filename, self.ALERT)
        self.harness.charm.loki_consumer._reinitialize_alert_rules()
        relation = self.harness.charm.model.get_relation("logging")
        self.assertNotEqual(
            relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS
        )

        # WHEN the alerts dir itself is deleted
        self.sandbox.remove(alert_filename)
        self.sandbox.rmdir(self.alert_rules_path)

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is empty again
        relation = self.harness.charm.model.get_relation("logging")
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)
