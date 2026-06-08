# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import patch

import pytest
import yaml
from ops.testing import ActiveStatus, BlockedStatus, Relation, State


# For the sake of reducing complexity in this test,
# we assume that any rule containing the string "INVALID" in its expression
# is invalid and should cause the entire relation's rules to be rejected.
def _validate_rule_file(rules):
    """Fail validation if any rule in the relation payload contains the INVALID marker."""
    for group in rules.get("groups", []):
        for rule in group.get("rules", []):
            if "INVALID" in rule.get("expr", ""):
                return False, "parse error"
    return True, ""


# Helper function to create a Relation with specified alert rules.
# The `with_invalid_rule` parameter controls whether one of the rules in the relation is intentionally invalid.
def _relation(name: str, app_name: str, with_invalid_rule: bool) -> Relation:
    invalid_expr = 'sum(rate({job="foo"}[5m])) > INVALID'
    valid_expr_1 = f'sum(rate({{job="{name}"}}[5m])) > 0'
    valid_expr_2 = f'sum(rate({{job="{name}"}}[10m])) > 0'

    group_rules = [
        {
            "alert": f"{name.capitalize()}ValidRuleA",
            "expr": valid_expr_1,
            "for": "1m",
            "labels": {"severity": "warning"},
            "annotations": {"summary": f"{name}-valid-a"},
        },
        {
            "alert": f"{name.capitalize()}ValidRuleB",
            "expr": invalid_expr if with_invalid_rule else valid_expr_2,
            "for": "1m",
            "labels": {"severity": "warning"},
            "annotations": {"summary": f"{name}-valid-b"},
        },
    ]

    alert_rules = {"groups": [{"name": f"{name}-group", "rules": group_rules}]}
    metadata = {
        "model": "test",
        "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
        "application": app_name,
        "charm_name": f"{app_name}-charm",
    }
    return Relation(
        "logging",
        remote_app_name=app_name,
        remote_app_data={"alert_rules": json.dumps(alert_rules), "metadata": json.dumps(metadata)},
    )


@pytest.mark.parametrize(
    "rel1_invalid, rel2_invalid, expected_group_names",
    [
        (False, False, {"rel1-group", "rel2-group"}),
        (False, True, {"rel1-group"}),
        (True, True, set()),
    ],
)
def test_relation_level_filtering(context, loki_container, rel1_invalid, rel2_invalid, expected_group_names):
    # Each relation contributes one alert group with two rules.
    # If any rule in that relation payload is invalid, the whole relation payload is dropped.
    rel1 = _relation("rel1", "app-one", rel1_invalid)
    rel2 = _relation("rel2", "app-two", rel2_invalid)
    state_in = State(relations=[rel1, rel2], containers=[loki_container], leader=True)

    # WHEN a logging relation-changed event is processed
    with patch(
        "charms.loki_k8s.v1.loki_push_api.CosTool.validate_alert_rules",
        side_effect=_validate_rule_file,
    ), patch("charm.LokiOperatorCharm._check_alert_rules", return_value=None):
        state_out = context.run(context.on.relation_changed(rel1), state_in)

    # THEN relation payloads with any invalid rule are dropped, valid relation payloads are kept.
    fs = state_out.get_container("loki").get_filesystem(context)

    # Loki monolithic stores rules in /loki/rules/fake.
    rules_dir = fs.joinpath("loki", "rules", "fake")
    if not rules_dir.exists():
        # No valid relation payload survived filtering, so no rules directory gets populated.
        assert expected_group_names == set()
        # the status must be blocked.
        assert isinstance(state_out.unit_status, BlockedStatus)
        return

    rule_files = sorted(path for path in rules_dir.iterdir() if path.is_file())
    # One file is written per surviving relation payload.
    assert len(rule_files) == len(expected_group_names)

    written_group_names = set()
    for rule_file in rule_files:
        written_rules = yaml.safe_load(rule_file.read_text())
        for group in written_rules["groups"]:
            written_group_names.add(group["name"])

    assert written_group_names == expected_group_names
    # If only one file is written, that means the other file contained an invalid rule.
    # So, we must assert that the charm was correctly blocked in that case.
    if len(written_group_names) == 1:
        assert isinstance(state_out.unit_status, BlockedStatus)
    elif len(written_group_names) == 2:
        # If both files are written, then no invalid rules were present, so the charm should not be active.
        assert isinstance(state_out.unit_status, ActiveStatus)
