# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import textwrap
import unittest
from pathlib import Path

import yaml
from charms.loki_k8s.v0.loki_push_api import AlertRules, LokiPushApiConsumer
from cosl import JujuTopology
from fs.tempfs import TempFS
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness


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
        self._stored.set_default(endpoint_events=0)

        self.loki_consumer = LokiPushApiConsumer(self)
        self.framework.observe(
            self.loki_consumer.on.loki_push_api_endpoint_joined, self.endpoint_events
        )

    def endpoint_events(self, _):
        self._stored.endpoint_events += 1

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"  # type: ignore
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

    def test_on_logging_relation_changed_no_leader(self):
        self.harness.set_leader(False)
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.assertEqual(self.harness.update_relation_data(rel_id, "promtail", {}), None)

    def test_on_logging_relation_changed_no_unit(self):
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

    def test_3_provider_units_related_scaled_down_to_0(self):
        rel_id = self.harness.add_relation("logging", "loki")

        # Add 3 Loki units
        for i in range(3):
            loki_unit = f"loki/{i}"
            endpoint = f"http://loki-{i}:3100/loki/api/v1/push"
            data = json.dumps({"url": f"{endpoint}"})
            self.harness.add_relation_unit(rel_id, loki_unit)
            self.harness.update_relation_data(
                rel_id,
                loki_unit,
                {"endpoint": data},
            )

        # Check we have 3 Loki endpoints
        self.assertEqual(len(self.harness.charm.loki_consumer.loki_endpoints), 3)

        # Check each endpoint is a dict, has a "url" key and starts with "http://"
        for endpoint_dict in self.harness.charm.loki_consumer.loki_endpoints:
            self.assertIsInstance(endpoint_dict, dict)
            self.assertTrue(list(endpoint_dict.keys())[0], "url")
            self.assertTrue(endpoint_dict["url"].startswith("http://"))

        # Remove Loki units
        for i in range(3):
            loki_unit = f"loki/{i}"
            self.harness.remove_relation_unit(rel_id, loki_unit)

        # Check we have no more endpoint
        self.assertAlmostEqual(len(self.harness.charm.loki_consumer.loki_endpoints), 0)

    def test_on_upgrade_charm_endpoint_joined_event_fired_for_leader(self):
        self.harness.set_leader(True)

        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.assertEqual(self.harness.charm._stored.endpoint_events, 1)

        self.harness.update_relation_data(
            rel_id,
            "promtail",
            {"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        )

        self.assertEqual(self.harness.charm._stored.endpoint_events, 2)

    def test_on_upgrade_charm_endpoint_joined_event_fired_for_follower(self):
        self.harness.set_leader(False)

        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.assertEqual(self.harness.charm._stored.endpoint_events, 1)

        self.harness.update_relation_data(
            rel_id,
            "promtail",
            {"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        )
        self.assertEqual(self.harness.charm._stored.endpoint_events, 2)


class TestReloadAlertRules(unittest.TestCase):
    """Feature: Consumer charm can manually invoke reloading of alerts.

    Background: In use cases such as cos-configuration-k8s-operator, the last hook can fire before
    the alert files show up on disk. In that case relation data would remain empty of alerts. To
    circumvent that, a public method for reloading alert rules is offered.
    """

    NO_ALERTS = json.dumps({})  # relation data representation for the case of "no alerts"

    # use a short-form free-standing alert, for brevity
    ALERT = yaml.safe_dump({"alert": "free_standing", "expr": "avg(some_vector[5m]) > 5"})

    RENDERED_ALERT_WITHOUT_LABELS = {
        "groups": [
            {
                "name": "alert_alerts",
                "rules": [
                    {"alert": "free_standing", "expr": "avg(some_vector[5m]) > 5", "labels": {}}
                ],
            }
        ]
    }

    def setUp(self):
        # override the default ordering, since each of these steps depends on the
        # state of the previous test

        # The "GIVEN" statements explicitly work against the way unittest is designed, and it is
        # only through sheer luck that they have worked thus far
        unittest.TestLoader.sortTestMethodsUsing = None  # type: ignore

        self.sandbox = TempFS("rule_files", auto_clean=True)
        self.addCleanup(self.sandbox.close)
        alert_rules_path = self.sandbox.getsyspath("/")

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
                    self,
                    alert_rules_path=alert_rules_path,
                    recursive=True,
                    skip_alert_topology_labeling=True,
                )

        self.harness = Harness(ConsumerCharm, meta=ConsumerCharm.metadata_yaml)
        # self.harness = Harness(FakeConsumerCharm, meta=FakeConsumerCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()
        self.harness.set_leader(True)
        self.rel_id = self.harness.add_relation("logging", "loki")

        # need to manually emit relation changed
        # https://github.com/canonical/operator/issues/682
        self.harness.charm.on.logging_relation_joined.emit(
            self.harness.charm.model.get_relation("logging")
        )

    def test_reload_when_dir_is_still_empty_changes_nothing(self):
        """Scenario: The reload method is called when the alerts dir is still empty."""
        # GIVEN relation data contains no alerts
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

        # WHEN no rule files are present

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is unchanged
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

    def test_reload_after_dir_is_populated_updates_relation_data(self):
        """Scenario: The reload method is called after some alert files are added."""
        # GIVEN relation data contains no alerts
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

        # WHEN some rule files are added to the alerts dir
        self.sandbox.writetext("alert.rule", self.ALERT)

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is updated
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertNotEqual(
            relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS
        )

    def test_reload_after_dir_is_emptied_updates_relation_data(self):
        """Scenario: The reload method is called after all the loaded alert files are removed."""
        # GIVEN alert files are present and relation data contains respective alerts
        self.sandbox.writetext("alert.rule", self.ALERT)
        self.harness.charm.loki_consumer._reinitialize_alert_rules()
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(
            json.loads(relation.data[self.harness.charm.app].get("alert_rules", "")),
            self.RENDERED_ALERT_WITHOUT_LABELS,
        )

        # WHEN all rule files are deleted from the alerts dir
        self.sandbox.clean()

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is empty again
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

    def test_reload_after_dir_itself_removed_updates_relation_data(self):
        """Scenario: The reload method is called after the alerts dir doesn't exist anymore."""
        # GIVEN alert files are present and relation data contains respective alerts
        self.sandbox.writetext("alert.rule", self.ALERT)
        self.harness.charm.loki_consumer._reinitialize_alert_rules()
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertNotEqual(
            relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS
        )

        # WHEN the alerts dir itself is deleted
        self.sandbox.clean()

        # AND the reload method is called
        self.harness.charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is empty again
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)


class TestAlertRuleNaming(unittest.TestCase):
    """AlertRules should return sanitized names for any given relative path.

    It is potentially risky to include any characters which may be path separators, drive
    separators on Windows, or `..|...` in names, since the behavior of Pebble pushing or
    otherwise writing is not predictable, and we can mitigate side_channel attacks.
    """

    PATHS = {
        r"src/alert_rules/foo.rule": "testing_20ce8299_tester_render_alerts",
        r"src/alert_rules/a/foo.rule": "testing_20ce8299_tester_a_render_alerts",
        r"src/alert_rules/a/b/foo.rule": "testing_20ce8299_tester_a_b_render_alerts",
        r"src/alert_rules/../../proc/cpuinfo": "testing_20ce8299_tester_proc_render_alerts",
        r"src/alert_rules/../../../sys/class/net": "testing_20ce8299_tester_sys_class_render_alerts",
    }

    def test_path_transformation(self):
        topology = JujuTopology.from_dict(
            {
                "model": "testing",
                "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
                "application": "tester",
                "unit": "tester/0",
            }
        )

        ar = AlertRules(topology)

        for path, rename in self.PATHS.items():
            val = ar._group_name(Path("src/alert_rules"), path, "render")
            self.assertEqual(val, rename)


class TestAlertRuleFormat(unittest.TestCase):
    """Feature: Consumer lib should warn when encountering invalid rules files.

    Background: It is not easy to determine the validity of rule files, but some cases are trivial:
      - empty files
      - files made up of only white-spaces that yaml.safe_load parses as None (space, newline)

    In those cases a warning should be emitted.
    """

    NO_ALERTS = json.dumps({})  # relation data representation for the case of "no alerts"

    def setUp(self):
        self.sandbox = TempFS("consumer_rule_files", auto_clean=True)
        self.addCleanup(self.sandbox.close)

        alert_rules_path = self.sandbox.getsyspath("/")

        class ConsumerCharm(CharmBase):
            metadata_yaml = textwrap.dedent(
                """
                name: loki-consumer-k8s
                requires:
                  logging:
                    interface: loki_push_api
                peers:
                  replicas:
                    interface: consumer_charm_replica
                """
            )

            def __init__(self, *args, **kwargs):
                super().__init__(*args)
                self._port = 3100
                self.loki_consumer = LokiPushApiConsumer(
                    self, alert_rules_path=alert_rules_path, recursive=True
                )

        self.harness = Harness(ConsumerCharm, meta=ConsumerCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)

        self.peer_rel_id = self.harness.add_relation("replicas", self.harness.model.app.name)
        self.harness.set_model_name("20ce8299-3634-4bef-8bd8-5ace6c8816b4")
        self.harness.set_leader(True)

        self.rel_id = self.harness.add_relation(relation_name="logging", remote_app="loki")
        self.harness.add_relation_unit(self.rel_id, "loki/0")

    def test_empty_rule_files_are_dropped_and_produce_an_error(self):
        """Scenario: Consumer charm attempts to forward an empty rule file."""
        # GIVEN a bunch of empty rule files (and ONLY empty rule files)
        self.sandbox.writetext("empty.rule", "")
        self.sandbox.writetext("whitespace1.rule", " ")
        self.sandbox.writetext("whitespace2.rule", "\n")
        self.sandbox.writetext("whitespace3.rule", "\r\n")

        # WHEN charm starts
        with self.assertLogs(level="ERROR") as logger:
            self.harness.begin_with_initial_hooks()

        # THEN relation data is empty (empty rule files do not get forwarded in any way)
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

        # AND an error message is recorded for every empty file
        logger_output = "\n".join(logger.output)  # type: ignore
        self.assertIn("empty.rule", logger_output)
        self.assertIn("whitespace1.rule", logger_output)
        self.assertIn("whitespace2.rule", logger_output)
        self.assertIn("whitespace3.rule", logger_output)

    def test_rules_files_with_invalid_yaml_are_dropped_and_produce_an_error(self):
        """Scenario: Consumer charm attempts to forward a rule file which is invalid yaml."""
        # GIVEN a bunch of invalid yaml rule files (and ONLY invalid yaml rule files)
        self.sandbox.writetext("tab.rule", "\t")
        self.sandbox.writetext("multicolon.rule", "this: is: not: yaml")

        # WHEN charm starts
        with self.assertLogs(level="ERROR") as logger:
            self.harness.begin_with_initial_hooks()

        # THEN relation data is empty (invalid rule files do not get forwarded in any way)
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        self.assertEqual(relation.data[self.harness.charm.app].get("alert_rules"), self.NO_ALERTS)

        # AND an error message is recorded for every invalid file
        logger_output = "\n".join(logger.output)  # type: ignore
        self.assertIn("tab.rule", logger_output)
        self.assertIn("multicolon.rule", logger_output)

    def test_rules_have_correct_labels(self):
        unlabeled_rule = {
            "groups": [
                {
                    "name": "alert_on_error",
                    "rules": [
                        {
                            "alert": "alert_on_error",
                            "expr": 'rate({%%juju_topology%%} |= "ERROR" [5m]) > 0',
                            "for": "1m",
                            "labels": {
                                "severity": "critical",
                            },
                            "annotations": {"summary": "Logs found at ERROR level"},
                        }
                    ],
                }
            ]
        }
        self.sandbox.writetext("error.rules", yaml.dump(unlabeled_rule))
        self.harness.begin_with_initial_hooks()
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        rules = json.loads(relation.data[self.harness.charm.app].get("alert_rules", ""))
        expr = rules["groups"][0]["rules"][0]["expr"]
        self.assertIn("juju_model", expr)
        self.assertIn("juju_model_uuid", expr)
        self.assertIn("juju_application", expr)
        self.assertIn("juju_charm", expr)
        self.assertNotIn("juju_unit", expr)
        self.assertEqual(
            set(rules["groups"][0]["rules"][0]["labels"]),
            {"juju_application", "juju_charm", "juju_model", "juju_model_uuid", "severity"},
        )

    def test_rules_have_correct_labels_when_unit_is_set(self):
        unlabeled_rule = {
            "groups": [
                {
                    "name": "alert_on_error",
                    "rules": [
                        {
                            "alert": "alert_on_error",
                            "expr": 'rate({%%juju_topology%%, juju_unit="app/0"} |= "ERROR" [5m]) > 0',
                            "for": "1m",
                            "labels": {
                                "severity": "critical",
                                "juju_unit": "app/0",
                            },
                            "annotations": {"summary": "Logs found at ERROR level"},
                        }
                    ],
                }
            ]
        }
        self.sandbox.writetext("error.rules", yaml.dump(unlabeled_rule))
        self.harness.begin_with_initial_hooks()
        relation = self.harness.charm.model.get_relation("logging")
        assert relation
        rules = json.loads(relation.data[self.harness.charm.app].get("alert_rules", ""))
        expr = rules["groups"][0]["rules"][0]["expr"]
        self.assertIn("juju_model", expr)
        self.assertIn("juju_model_uuid", expr)
        self.assertIn("juju_application", expr)
        self.assertIn("juju_charm", expr)
        self.assertIn("juju_unit", expr)
        self.assertEqual(
            set(rules["groups"][0]["rules"][0]["labels"]),
            {
                "juju_application",
                "juju_charm",
                "juju_model",
                "juju_model_uuid",
                "severity",
                "juju_unit",
            },
        )
