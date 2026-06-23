# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for LokiPushApiProvider v1 alert rules topology injection."""

import json

import pytest
from charms.loki_k8s.v1.loki_push_api import LokiPushApiProvider
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Context
from scenario import Relation, State

METADATA = {
    "model": "consumer-model",
    "model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
    "application": "promtail",
    "charm_name": "charm-k8s",
}

# Alert rules with juju_charm in labels (simulating what a subordinate would send)
ALERT_RULES_WITH_CHARM = {
    "groups": [
        {
            "name": "test_model_20ce8299_test_app_alerts",
            "rules": [
                {
                    "alert": "HighPercentageError",
                    "expr": 'sum(rate({job=~".+"} |= "error" [5m])) by (job)',
                    "for": "0m",
                    "labels": {
                        "severity": "critical",
                        "juju_model": "test-model",
                        "juju_model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
                        "juju_application": "test-app",
                        "juju_charm": "principal-charm",
                    },
                    "annotations": {
                        "summary": "High error rate",
                    },
                },
            ],
        }
    ]
}

FAKE_LOKI_META = {
    "name": "loki",
    "containers": {"loki": {"resource": "loki-image"}},
    "provides": {"logging": {"interface": "loki_push_api"}},
    "requires": {"alertmanager": {"interface": "alertmanager_dispatch"}},
}


class FakeLokiCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self.loki_provider = LokiPushApiProvider(
            self,
            address="10.0.0.1",
            port=3100,
            scheme="http",
            path="/loki/api/v1/push",
        )
        self._stored.set_default(event_count=0)


@pytest.fixture
def provider_context():
    return Context(FakeLokiCharm, meta=FAKE_LOKI_META)


def test_alerts_excludes_juju_charm_from_expression(provider_context):
    """Test that juju_charm is NOT injected into alert rule expressions.

    When alert rules come from a subordinate charm (like otelcol), the logs
    are labeled with juju_charm=<subordinate> but the rules have
    juju_charm=<principal> in labels. If juju_charm were injected into the
    expression, alerts would never fire due to the mismatch.

    The fix ensures only juju_model, juju_model_uuid, and juju_application
    are injected into expressions (matching alert_expression_dict behavior).
    """
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(ALERT_RULES_WITH_CHARM),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        charm = mgr.charm
        alerts = charm.loki_provider.alerts

        assert len(alerts) == 1
        alert_rules = list(alerts.values())[0]
        expr = alert_rules["groups"][0]["rules"][0]["expr"]

        # juju_charm should NOT be in the expression
        assert "juju_charm" not in expr, (
            f"juju_charm should not be injected into alert expressions, got: {expr}"
        )

        # But the core topology labels SHOULD be in the expression
        assert 'juju_model="test-model"' in expr
        assert 'juju_model_uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"' in expr
        assert 'juju_application="test-app"' in expr

        # juju_charm should still be in the labels (for informational purposes)
        labels = alert_rules["groups"][0]["rules"][0]["labels"]
        assert labels.get("juju_charm") == "principal-charm"


def test_alerts_excludes_juju_unit_from_expression(provider_context):
    """Test that juju_unit is NOT injected into alert rule expressions.

    Alert rules are forwarded over app data (one copy per app), so having
    a juju_unit matcher would exclude alerts from all other units.
    """
    alert_rules_with_unit = {
        "groups": [
            {
                "name": "test_alerts",
                "rules": [
                    {
                        "alert": "TestAlert",
                        "expr": 'sum(rate({job=~".+"}[5m]))',
                        "labels": {
                            "juju_model": "test-model",
                            "juju_model_uuid": "20ce8299-3634-4bef-8bd8-5ace6c8816b4",
                            "juju_application": "test-app",
                            "juju_unit": "test-app/0",
                        },
                    },
                ],
            }
        ]
    }

    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(alert_rules_with_unit),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        charm = mgr.charm
        alerts = charm.loki_provider.alerts

        assert len(alerts) == 1
        expr = list(alerts.values())[0]["groups"][0]["rules"][0]["expr"]

        # juju_unit should NOT be in the expression
        assert "juju_unit" not in expr, (
            f"juju_unit should not be injected into alert expressions, got: {expr}"
        )
