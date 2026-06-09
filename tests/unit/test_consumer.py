# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import shutil
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from charms.loki_k8s.v0.loki_push_api import AlertRules, CosTool, LokiPushApiConsumer
from cosl import JujuTopology
from fs.tempfs import TempFS
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Context
from scenario import Model, PeerRelation, Relation, State

FAKE_CONSUMER_META = {
    "name": "fake-consumer",
    "containers": {"promtail": {"resource": "promtail-image"}},
    "requires": {"logging": {"interface": "loki_push_api"}},
    "peers": {"replicas": {"interface": "fake_consumer_replica"}},
}


class FakeConsumerCharm(CharmBase):
    _stored = StoredState()

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
        loki_push_api = f"http://{self.unit_ip}:{self._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP."""
        return "10.1.2.3"


@pytest.fixture
def consumer_context():
    return Context(FakeConsumerCharm, meta=FAKE_CONSUMER_META)


def test_on_logging_relation_changed_no_leader(consumer_context):
    """Test relation changed when not leader."""
    logging_rel = Relation("logging", remote_app_name="promtail", remote_units_data={0: {}})
    state = State(leader=False, relations=[logging_rel])

    # Should not raise any errors
    consumer_context.run(consumer_context.on.relation_changed(logging_rel), state)


def test_on_logging_relation_changed_no_unit(consumer_context):
    """Test relation changed with unit data."""
    logging_rel = Relation(
        "logging",
        remote_app_name="promtail",
        remote_app_data={"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        remote_units_data={0: {}},
    )
    state = State(leader=True, relations=[logging_rel])

    # Should not raise any errors
    consumer_context.run(consumer_context.on.relation_changed(logging_rel), state)


def test_multiple_provider_units_related(consumer_context):
    """Test with 3 provider units."""
    # GIVEN 3 provider units are related
    logging_rel = Relation(
        "logging",
        remote_app_name="loki",
        remote_units_data={
            0: {"endpoint": json.dumps({"url": "http://loki-0:3100/loki/api/v1/push"})},
            1: {"endpoint": json.dumps({"url": "http://loki-1:3100/loki/api/v1/push"})},
            2: {"endpoint": json.dumps({"url": "http://loki-2:3100/loki/api/v1/push"})},
        },
    )
    state = State(leader=True, relations=[logging_rel])
    with consumer_context(consumer_context.on.relation_changed(logging_rel), state) as mgr:
        charm = mgr.charm
        # THEN we have 3 Loki endpoints
        assert len(charm.loki_consumer.loki_endpoints) == 3

        # Check each endpoint is a dict, has a "url" key and starts with "http://"
        for endpoint_dict in charm.loki_consumer.loki_endpoints:
            assert isinstance(endpoint_dict, dict)
            assert "url" in endpoint_dict
            assert endpoint_dict["url"].startswith("http://")


def test_on_upgrade_charm_endpoint_joined_event_fired_for_leader(consumer_context):
    """Test that endpoint_joined event fires for leader."""
    logging_rel = Relation(
        "logging",
        remote_app_name="promtail",
        remote_units_data={0: {}},
    )
    state = State(leader=True, relations=[logging_rel])

    # WHEN a provider unit joins THEN endpoint_joined fires once
    with consumer_context(consumer_context.on.relation_joined(logging_rel), state) as mgr:
        state = mgr.run()
        assert mgr.charm._stored.endpoint_events == 1

    # WHEN the provider then publishes its push-api endpoint (relation-changed)
    rel = replace(
        state.get_relation(logging_rel.id),
        remote_app_data={"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
    )
    state = replace(state, relations={rel})
    with consumer_context(consumer_context.on.relation_changed(rel), state) as mgr:
        mgr.run()
        # THEN endpoint_joined fires again
        assert mgr.charm._stored.endpoint_events == 2


def test_on_upgrade_charm_endpoint_joined_event_fired_for_follower(consumer_context):
    """Test that endpoint_joined event fires for follower."""
    logging_rel = Relation(
        "logging",
        remote_app_name="promtail",
        remote_units_data={0: {}},
    )
    state = State(leader=False, relations=[logging_rel])

    # WHEN a provider unit joins THEN endpoint_joined fires once
    with consumer_context(consumer_context.on.relation_joined(logging_rel), state) as mgr:
        state = mgr.run()
        assert mgr.charm._stored.endpoint_events == 1

    # WHEN the provider then publishes its push-api endpoint (relation-changed)
    rel = replace(
        state.get_relation(logging_rel.id),
        remote_app_data={"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
    )
    state = replace(state, relations={rel})
    with consumer_context(consumer_context.on.relation_changed(rel), state) as mgr:
        mgr.run()
        # THEN endpoint_joined fires again
        assert mgr.charm._stored.endpoint_events == 2


# --- TestReloadAlertRules ---


@pytest.fixture
def alert_rules_sandbox():
    """Fixture that provides a temporary directory for alert rule files."""
    sandbox = TempFS("rule_files", auto_clean=True)
    yield sandbox
    sandbox.close()


@pytest.fixture
def reload_context(alert_rules_sandbox):
    """Context for testing alert rule reload functionality."""
    alert_rules_path = alert_rules_sandbox.getsyspath("/")

    class ReloadConsumerCharm(CharmBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self._port = 3100
            self.loki_consumer = LokiPushApiConsumer(
                self,
                alert_rules_path=alert_rules_path,
                recursive=True,
                skip_alert_topology_labeling=True,
            )

    meta = {
        "name": "reload-consumer",
        "requires": {"logging": {"interface": "loki_push_api"}},
    }
    return Context(ReloadConsumerCharm, meta=meta)


NO_ALERTS = json.dumps({})
ALERT = yaml.safe_dump({"alert": "free_standing", "expr": "avg(some_vector[5m]) > 5"})


def test_reload_when_dir_is_still_empty_changes_nothing(reload_context):
    """Scenario: The reload method is called when the alerts dir is still empty."""
    ctx = reload_context
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel])

    with ctx(ctx.on.relation_joined(logging_rel), state) as mgr:
        mgr.run()
        charm = mgr.charm
        relation = charm.model.get_relation("logging")
        assert relation

        # GIVEN relation data contains no alerts
        assert relation.data[charm.app].get("alert_rules") == NO_ALERTS

        # WHEN the reload method is called
        charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is unchanged
        assert relation.data[charm.app].get("alert_rules") == NO_ALERTS


def test_reload_after_dir_is_populated_updates_relation_data(reload_context, alert_rules_sandbox):
    """Scenario: The reload method is called after some alert files are added."""
    ctx = reload_context
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel])

    with ctx(ctx.on.relation_joined(logging_rel), state) as mgr:
        mgr.run()
        charm = mgr.charm
        relation = charm.model.get_relation("logging")
        assert relation

        # GIVEN relation data contains no alerts
        assert relation.data[charm.app].get("alert_rules") == NO_ALERTS

        # WHEN some rule files are added to the alerts dir
        alert_rules_sandbox.writetext("alert.rule", ALERT)

        # AND the reload method is called
        charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is updated
        assert relation.data[charm.app].get("alert_rules") != NO_ALERTS


def test_reload_after_dir_is_emptied_updates_relation_data(reload_context, alert_rules_sandbox):
    """Scenario: The reload method is called after all the loaded alert files are removed."""
    ctx = reload_context
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel])

    with ctx(ctx.on.relation_joined(logging_rel), state) as mgr:
        mgr.run()
        charm = mgr.charm
        relation = charm.model.get_relation("logging")
        assert relation

        # GIVEN alert files are present and reload has populated the relation data
        alert_rules_sandbox.writetext("alert.rule", ALERT)
        charm.loki_consumer._reinitialize_alert_rules()
        assert relation.data[charm.app].get("alert_rules") != NO_ALERTS

        # WHEN all rule files are deleted from the alerts dir
        alert_rules_sandbox.remove("alert.rule")

        # AND the reload method is called
        charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is empty again
        assert relation.data[charm.app].get("alert_rules") == NO_ALERTS


def test_reload_after_dir_itself_removed_updates_relation_data(reload_context, alert_rules_sandbox):
    """Scenario: The reload method is called after the alerts dir doesn't exist anymore."""
    ctx = reload_context
    alert_rules_path = alert_rules_sandbox.getsyspath("/")
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel])

    with ctx(ctx.on.relation_joined(logging_rel), state) as mgr:
        mgr.run()
        charm = mgr.charm
        relation = charm.model.get_relation("logging")
        assert relation

        # GIVEN alert files are present and reload has populated the relation data
        alert_rules_sandbox.writetext("alert.rule", ALERT)
        charm.loki_consumer._reinitialize_alert_rules()
        assert relation.data[charm.app].get("alert_rules") != NO_ALERTS

        # WHEN the alerts dir itself is deleted
        shutil.rmtree(alert_rules_path)

        # AND the reload method is called
        charm.loki_consumer._reinitialize_alert_rules()

        # THEN relation data is empty again (and no error is raised)
        assert relation.data[charm.app].get("alert_rules") == NO_ALERTS

    # Recreate the dir so the sandbox fixture can tear down cleanly.
    Path(alert_rules_path).mkdir(parents=True, exist_ok=True)


# --- TestAlertRuleNaming ---


PATHS = {
    r"src/alert_rules/foo.rule": "testing_20ce8299_tester_render_alerts",
    r"src/alert_rules/a/foo.rule": "testing_20ce8299_tester_a_render_alerts",
    r"src/alert_rules/a/b/foo.rule": "testing_20ce8299_tester_a_b_render_alerts",
    r"src/alert_rules/../../proc/cpuinfo": "testing_20ce8299_tester_proc_render_alerts",
    r"src/alert_rules/../../../sys/class/net": "testing_20ce8299_tester_sys_class_render_alerts",
}


def test_path_transformation():
    """Test that alert rule paths are properly transformed."""
    topology = JujuTopology.from_dict(
        {
            "model": "testing",
            "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
            "application": "tester",
            "unit": "tester/0",
        }
    )

    ar = AlertRules(topology)

    for path, rename in PATHS.items():
        val = ar._group_name(Path("src/alert_rules"), path, "render")
        assert val == rename


# --- TestAlertRuleFormat ---


@pytest.fixture
def format_context():
    """Context for testing alert rule format validation."""
    sandbox = TempFS("consumer_rule_files", auto_clean=True)

    # Reset CosTool cache and mock processor
    CosTool._path = None
    CosTool._disabled = False

    alert_rules_path = sandbox.getsyspath("/")

    class FormatConsumerCharm(CharmBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self._port = 3100
            self.loki_consumer = LokiPushApiConsumer(
                self, alert_rules_path=alert_rules_path, recursive=True
            )

    meta = {
        "name": "loki-consumer-k8s",
        "requires": {"logging": {"interface": "loki_push_api"}},
        "peers": {"replicas": {"interface": "consumer_charm_replica"}},
    }
    yield Context(FormatConsumerCharm, meta=meta), sandbox
    sandbox.close()


def test_empty_rule_files_are_dropped_and_produce_an_error(format_context, caplog):
    """Scenario: Consumer charm attempts to forward an empty rule file."""
    ctx, sandbox = format_context

    # GIVEN a bunch of empty rule files (and ONLY empty rule files)
    sandbox.writetext("empty.rule", "")
    sandbox.writetext("whitespace1.rule", " ")
    sandbox.writetext("whitespace2.rule", "\n")
    sandbox.writetext("whitespace3.rule", "\r\n")

    peer_rel = PeerRelation("replicas")
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel, peer_rel], model=Model(uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"))

    with patch("platform.processor", return_value="x86_64"):
        state_out = ctx.run(ctx.on.relation_joined(logging_rel), state)

    # THEN relation data is empty (empty rule files do not get forwarded in any way)
    rel = state_out.get_relation(logging_rel.id)
    assert rel.local_app_data.get("alert_rules") == NO_ALERTS

    # AND an error message is recorded for every empty file
    assert "empty.rule" in caplog.text
    assert "whitespace1.rule" in caplog.text
    assert "whitespace2.rule" in caplog.text
    assert "whitespace3.rule" in caplog.text


def test_rules_files_with_invalid_yaml_are_dropped_and_produce_an_error(format_context, caplog):
    """Scenario: Consumer charm attempts to forward a rule file which is invalid yaml."""
    ctx, sandbox = format_context

    # GIVEN a bunch of invalid yaml rule files (and ONLY invalid yaml rule files)
    sandbox.writetext("tab.rule", "\t")
    sandbox.writetext("multicolon.rule", "this: is: not: yaml")

    peer_rel = PeerRelation("replicas")
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel, peer_rel], model=Model(uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"))

    with patch("platform.processor", return_value="x86_64"):
        state_out = ctx.run(ctx.on.relation_joined(logging_rel), state)

    # THEN relation data is empty (invalid rule files do not get forwarded in any way)
    rel = state_out.get_relation(logging_rel.id)
    assert rel.local_app_data.get("alert_rules") == NO_ALERTS

    # AND an error message is recorded for every invalid file
    assert "tab.rule" in caplog.text
    assert "multicolon.rule" in caplog.text


def test_rules_have_correct_labels(format_context):
    """Test that rules have correct juju topology labels."""
    ctx, sandbox = format_context

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
    sandbox.writetext("error.rules", yaml.dump(unlabeled_rule))

    peer_rel = PeerRelation("replicas")
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel, peer_rel], model=Model(uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"))

    with patch("platform.processor", return_value="x86_64"):
        state_out = ctx.run(ctx.on.relation_joined(logging_rel), state)

    rel = state_out.get_relation(logging_rel.id)
    rules = json.loads(rel.local_app_data.get("alert_rules", ""))
    expr = rules["groups"][0]["rules"][0]["expr"]
    assert "juju_model" in expr
    assert "juju_model_uuid" in expr
    assert "juju_application" in expr
    assert "juju_charm" in expr
    assert "juju_unit" not in expr
    assert set(rules["groups"][0]["rules"][0]["labels"]) == {
        "juju_application",
        "juju_charm",
        "juju_model",
        "juju_model_uuid",
        "severity",
    }


def test_rules_have_correct_labels_when_unit_is_set(format_context):
    """Test that rules have correct juju topology labels including unit when set."""
    ctx, sandbox = format_context

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
    sandbox.writetext("error.rules", yaml.dump(unlabeled_rule))

    peer_rel = PeerRelation("replicas")
    logging_rel = Relation("logging", remote_app_name="loki", remote_units_data={0: {}})
    state = State(leader=True, relations=[logging_rel, peer_rel], model=Model(uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"))

    with patch("platform.processor", return_value="x86_64"):
        state_out = ctx.run(ctx.on.relation_joined(logging_rel), state)

    rel = state_out.get_relation(logging_rel.id)
    rules = json.loads(rel.local_app_data.get("alert_rules", ""))
    expr = rules["groups"][0]["rules"][0]["expr"]
    assert "juju_model" in expr
    assert "juju_model_uuid" in expr
    assert "juju_application" in expr
    assert "juju_charm" in expr
    assert "juju_unit" in expr
    assert set(rules["groups"][0]["rules"][0]["labels"]) == {
        "juju_application",
        "juju_charm",
        "juju_model",
        "juju_model_uuid",
        "severity",
        "juju_unit",
    }
