# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""BDD tests for alert_rule_customizations config option."""

from typing import Any, Dict, List
from unittest.mock import patch

import ops
import pytest
import yaml
from _alert_rule_customization_helpers import (
    _make_logging_relation,
    customization_status,
    read_all_rules,
)
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Context, State
from pytest_bdd import given, parsers, scenarios, then, when
from scenario import Container, Exec

from charm import LokiOperatorCharm

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def tautology(*_, **__) -> bool:
    return True


@pytest.fixture
def loki_charm_cls():
    with patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="test-namespace",
        _patch=tautology,
        is_ready=tautology,
    ):
        with patch("socket.getfqdn", new=lambda *args: "fqdn"):
            with patch("lightkube.core.client.GenericSyncClient"):
                yield LokiOperatorCharm


@pytest.fixture
def ctx(loki_charm_cls):
    return Context(loki_charm_cls)


@pytest.fixture
def loki_container():
    return Container(
        "loki",
        can_connect=True,
        execs={
            Exec(["update-ca-certificates", "--fresh"], return_code=0),
            Exec(["/usr/bin/loki", "-version"], return_code=0, stdout="loki, version 3.14159"),
        },
        layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
        service_statuses={"loki": ops.pebble.ServiceStatus.INACTIVE},
    )

scenarios("features/alert_rule_customizations.feature")

# ---------------------------------------------------------------------------
# Steps: Given
# ---------------------------------------------------------------------------


@given(
    "the charm provides the following alert rules:",
    target_fixture="base_state",
)
def given_alert_rules(docstring, ctx, loki_container):
    """Build a State with a logging relation carrying the given rule groups."""
    groups_by_name: Dict[str, List[Dict[str, Any]]] = yaml.safe_load(docstring)
    groups = [{"name": name, "rules": rules} for name, rules in groups_by_name.items()]
    relation = _make_logging_relation("app-alpha", groups)
    return {
        "ctx": ctx,
        "loki_container": loki_container,
        "relation": relation,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Steps: When
# ---------------------------------------------------------------------------


def _run_config_changed(base_state, docstring):
    """Apply the given customization string and return the output state."""
    ctx = base_state["ctx"]
    loki_container = base_state["loki_container"]
    relation = base_state["relation"]

    state_in = State(
        config={"alert_rule_customizations": docstring},
        relations=[relation],
        containers=[loki_container],
        leader=True,
    )

    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=None):
        state_out = ctx.run(ctx.on.relation_changed(relation), state_in)

    return state_out


@when(
    "the customization is set to:",
    target_fixture="state_out",
)
def when_customization_block(base_state, docstring):
    return _run_config_changed(base_state, docstring)


# ---------------------------------------------------------------------------
# Steps: Then
# ---------------------------------------------------------------------------


@then(parsers.parse('alert "{alert_name}" is not written'))
def then_alert_not_written(base_state, state_out, alert_name):
    ctx = base_state["ctx"]
    rules = read_all_rules(ctx, state_out)
    all_alerts = [r.get("alert") for group_rules in rules.values() for r in group_rules]
    assert alert_name not in all_alerts, (
        f"Expected alert '{alert_name}' to be absent but found it in: {all_alerts}"
    )


@then(parsers.parse('alert "{alert_name}" is written'))
def then_alert_is_written(base_state, state_out, alert_name):
    ctx = base_state["ctx"]
    rules = read_all_rules(ctx, state_out)
    all_alerts = [r.get("alert") for group_rules in rules.values() for r in group_rules]
    assert alert_name in all_alerts, (
        f"Expected alert '{alert_name}' to be present but not found in: {all_alerts}"
    )


@then(parsers.parse('alert "{alert_name}" has "{field}" equal to "{value}"'))
def then_alert_field_equals(base_state, state_out, alert_name, field, value):
    ctx = base_state["ctx"]
    rules = read_all_rules(ctx, state_out)
    for group_rules in rules.values():
        for rule in group_rules:
            if rule.get("alert") == alert_name:
                assert str(rule.get(field)) == value, (
                    f"Alert '{alert_name}' field '{field}': expected '{value}', got '{rule.get(field)}'"
                )
                return
    pytest.fail(f"Alert '{alert_name}' not found in written rules")


@then(parsers.parse('alert "{alert_name}" has label "{label_key}" equal to "{label_value}"'))
def then_alert_label_equals(base_state, state_out, alert_name, label_key, label_value):
    ctx = base_state["ctx"]
    rules = read_all_rules(ctx, state_out)
    for group_rules in rules.values():
        for rule in group_rules:
            if rule.get("alert") == alert_name:
                labels = rule.get("labels", {})
                assert labels.get(label_key) == label_value, (
                    f"Alert '{alert_name}' label '{label_key}': "
                    f"expected '{label_value}', got '{labels.get(label_key)}'"
                )
                return
    pytest.fail(f"Alert '{alert_name}' not found in written rules")


@then("the charm is in BlockedStatus for alert_rule_customizations")
def then_customization_blocked(base_state, state_out):
    status = customization_status(state_out)
    assert isinstance(status, BlockedStatus), (
        f"Expected BlockedStatus for alert_rule_customizations, got {type(status).__name__}: {status}"
    )


@then("the charm is in ActiveStatus for alert_rule_customizations")
def then_customization_active(base_state, state_out):
    status = customization_status(state_out)
    assert isinstance(status, ActiveStatus), (
        f"Expected ActiveStatus for alert_rule_customizations, got {type(status).__name__}: {status}"
    )


@then("all provided alert rules are still written unchanged")
def then_rules_unchanged(base_state, state_out):
    ctx = base_state["ctx"]
    groups = base_state["groups"]
    rules = read_all_rules(ctx, state_out)

    expected_alerts = {r["alert"] for g in groups for r in g["rules"]}
    written_alerts = {r.get("alert") for group_rules in rules.values() for r in group_rules}

    # The lib injects topology labels, so we just check that all original alert names are present.
    assert expected_alerts.issubset(written_alerts), (
        f"Expected all alerts {expected_alerts} to be written, but got: {written_alerts}"
    )


@then("the written alert rules are unchanged")
def then_rules_same_as_baseline(base_state, state_out):
    """The output matches what we'd get with no customization applied."""
    ctx = base_state["ctx"]
    groups = base_state["groups"]
    rules = read_all_rules(ctx, state_out)

    expected_alerts = {r["alert"] for g in groups for r in g["rules"]}
    written_alerts = {r.get("alert") for group_rules in rules.values() for r in group_rules}

    assert expected_alerts.issubset(written_alerts), (
        f"Expected all original alerts {expected_alerts} to still be written; got {written_alerts}"
    )
