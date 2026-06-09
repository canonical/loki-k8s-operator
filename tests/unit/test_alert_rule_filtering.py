# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import patch

from helpers import _written_group_names
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Relation, State

VALID_RELATION = Relation(
    "logging",
    remote_app_name="app-valid",
    remote_app_data={
        "alert_rules": json.dumps(
            {
                "groups": [
                    {
                        "name": "valid-group",
                        "rules": [
                            {
                                "alert": "ValidRuleA",
                                "expr": 'sum(rate({job="valid"}[5m])) > 0',
                                "for": "1m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "valid-a"},
                            },
                            {
                                "alert": "ValidRuleB",
                                "expr": 'sum(rate({job="valid"}[10m])) > 0',
                                "for": "1m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "valid-b"},
                            },
                        ],
                    }
                ]
            }
        ),
        "metadata": json.dumps(
            {
                "model": "test",
                "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
                "application": "app-valid",
                "charm_name": "app-valid-charm",
            }
        ),
    },
)

INVALID_RELATION = Relation(
    "logging",
    remote_app_name="app-invalid",
    remote_app_data={
        "alert_rules": json.dumps(
            {
                "groups": [
                    {
                        "name": "invalid-group",
                        "rules": [
                            {
                                "alert": "InvalidRuleA",
                                "expr": 'sum(rate({job="invalid"}[5m])) > INVALID',
                                "for": "1m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "invalid-a"},
                            },
                            {
                                "alert": "InvalidRuleB",
                                "expr": 'sum(rate({job="invalid"}[10m])) > 0',
                                "for": "1m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "invalid-b"},
                            },
                        ],
                    }
                ]
            }
        ),
        "metadata": json.dumps(
            {
                "model": "test",
                "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
                "application": "app-invalid",
                "charm_name": "app-invalid-charm",
            }
        ),
    },
)


def test_valid_relation_only(context, loki_container):
    # GIVEN one relation with only valid rules
    state_in = State(relations=[VALID_RELATION], containers=[loki_container], leader=True)

    # WHEN the relation changed event is processed
    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=None):
        state_out = context.run(context.on.relation_changed(VALID_RELATION), state_in)

    # THEN valid rules are written and unit remains active
    assert _written_group_names(context, state_out) == {"valid-group"}
    assert isinstance(state_out.unit_status, ActiveStatus)


def test_invalid_relation_only(context, loki_container):
    # GIVEN one relation where at least one rule is invalid
    state_in = State(relations=[INVALID_RELATION], containers=[loki_container], leader=True)

    # WHEN the relation changed event is processed
    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=None):
        state_out = context.run(context.on.relation_changed(INVALID_RELATION), state_in)

    # THEN invalid relation rules are not written and unit is blocked
    assert _written_group_names(context, state_out) == set()
    assert isinstance(state_out.unit_status, BlockedStatus)


def test_valid_and_invalid_relations(context, loki_container):
    # GIVEN one valid relation and one invalid relation
    state_in = State(
        relations=[VALID_RELATION, INVALID_RELATION], containers=[loki_container], leader=True
    )

    # WHEN the relation changed event is processed
    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=None):
        state_out = context.run(context.on.relation_changed(VALID_RELATION), state_in)

    # THEN only valid relation rules are written and unit is blocked due to invalid relation
    assert _written_group_names(context, state_out) == {"valid-group"}
    assert isinstance(state_out.unit_status, BlockedStatus)
