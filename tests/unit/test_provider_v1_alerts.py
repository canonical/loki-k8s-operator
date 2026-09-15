# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for LokiPushApiProvider v1 alert rules topology injection."""

import json

import pytest
from charms.loki_k8s.v1.loki_push_api import (
    ALERT_RULES_ENCODINGS_KEY,
    JSON_ENCODING,
    LZMA_ENCODING,
    SUPPORTED_ALERT_RULES_ENCODINGS,
    LokiPushApiProvider,
    _encode_alert_rules,
)
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

# Simple alert rules for compression tests
SIMPLE_ALERT_RULES = {
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


def test_alerts_decodes_lzma_compressed_payload(provider_context):
    """A compressed (LZMA + base64) alert_rules payload decodes correctly."""
    compressed = _encode_alert_rules(SIMPLE_ALERT_RULES, LZMA_ENCODING)

    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": compressed,
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
        assert alert_rules["groups"][0]["rules"][0]["alert"] == "TestAlert"


def test_alerts_decodes_legacy_plain_json_payload(provider_context):
    """A plain-JSON payload from a legacy consumer still decodes correctly."""
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(SIMPLE_ALERT_RULES),
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
        assert alert_rules["groups"][0]["rules"][0]["alert"] == "TestAlert"


def test_alerts_skips_corrupt_alert_rules(provider_context):
    """A corrupt alert_rules value is skipped, without raising."""
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": "not valid json, nor valid lzma/base64",
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        charm = mgr.charm
        alerts = charm.loki_provider.alerts

        assert alerts == {}


def test_alerts_skips_double_json_encoded_payload(provider_context):
    """A JSON string payload that is not a compressed blob is skipped cleanly.

    ``json.loads('"foo"')`` returns the Python string ``"foo"``, which then reaches
    the decompression step and fails there.
    """
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps("foo"),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        charm = mgr.charm
        alerts = charm.loki_provider.alerts

        assert alerts == {}


def test_alerts_skips_non_object_payload(provider_context):
    """A syntactically valid JSON payload that decodes to a list is skipped cleanly."""
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps([1, 2, 3]),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        charm = mgr.charm
        alerts = charm.loki_provider.alerts

        assert alerts == {}


def test_alerts_skips_unreadable_relation_but_returns_others(provider_context):
    """One relation with unreadable alert_rules doesn't prevent others from being read."""
    broken_relation = Relation(
        "logging",
        remote_app_name="broken-consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": "not valid json, nor valid lzma/base64",
        },
        remote_units_data={0: {}},
    )
    healthy_relation = Relation(
        "logging",
        remote_app_name="healthy-consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(SIMPLE_ALERT_RULES),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[broken_relation, healthy_relation])

    with provider_context(
        provider_context.on.relation_changed(healthy_relation), state
    ) as mgr:
        charm = mgr.charm
        alerts = charm.loki_provider.alerts

        assert len(alerts) == 1
        alert_rules = list(alerts.values())[0]
        assert alert_rules["groups"][0]["rules"][0]["alert"] == "TestAlert"


@pytest.mark.parametrize("event_name", ["relation_joined", "relation_changed"])
def test_provider_advertises_alert_rules_encodings_on_relation_events(
    provider_context, event_name
):
    """The provider (re)advertises supported alert rules encodings on relation events."""
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(SIMPLE_ALERT_RULES),
        },
        remote_units_data={0: {}},
    )
    state = State(leader=True, relations=[logging_relation])

    state_out = provider_context.run(
        getattr(provider_context.on, event_name)(logging_relation), state
    )

    relation = state_out.get_relation(logging_relation.id)
    advertised = relation.local_app_data[ALERT_RULES_ENCODINGS_KEY]
    assert json.loads(advertised) == list(SUPPORTED_ALERT_RULES_ENCODINGS)


@pytest.mark.parametrize("event_name", ["leader_elected", "upgrade_charm"])
def test_provider_advertises_alert_rules_encodings_on_lifecycle_events(
    provider_context, event_name
):
    """The provider (re)advertises supported alert rules encodings on lifecycle events.

    These events carry no relation, so the provider iterates over every existing
    relation to (re)publish the advertisement.
    """
    logging_relation = Relation("logging", remote_app_name="consumer")
    state = State(leader=True, relations=[logging_relation])

    state_out = provider_context.run(getattr(provider_context.on, event_name)(), state)

    relation = state_out.get_relation(logging_relation.id)
    advertised = relation.local_app_data[ALERT_RULES_ENCODINGS_KEY]
    assert json.loads(advertised) == list(SUPPORTED_ALERT_RULES_ENCODINGS)


def test_provider_does_not_advertise_encodings_when_not_leader(provider_context):
    """Non-leader units never write to app relation data."""
    logging_relation = Relation("logging", remote_app_name="consumer")
    state = State(leader=False, relations=[logging_relation])

    state_out = provider_context.run(
        provider_context.on.relation_joined(logging_relation), state
    )

    relation = state_out.get_relation(logging_relation.id)
    assert ALERT_RULES_ENCODINGS_KEY not in relation.local_app_data


def test_encode_alert_rules_json_default():
    """Default encoding is plain, sorted-keys JSON."""
    encoded = _encode_alert_rules(SIMPLE_ALERT_RULES, JSON_ENCODING)
    assert json.loads(encoded) == SIMPLE_ALERT_RULES
    # Plain JSON is readable directly.
    assert encoded.startswith("{")


def test_unknown_encoding_falls_back_to_json():
    """An encoding this library doesn't know about is treated as plain JSON.

    This keeps negotiation backward- and forward-compatible: an unrecognized encoding
    falls back to plain JSON, which every version of this library can read.
    """
    encoded = _encode_alert_rules(SIMPLE_ALERT_RULES, "brotli")
    assert json.loads(encoded) == SIMPLE_ALERT_RULES


@pytest.mark.parametrize("encoding", SUPPORTED_ALERT_RULES_ENCODINGS)
def test_encoding_is_deterministic(encoding):
    """The same rules, with keys in a different order, encode to identical bytes."""
    reordered = json.loads(json.dumps(SIMPLE_ALERT_RULES))
    rule = reordered["groups"][0]["rules"][0]
    reordered["groups"][0]["rules"][0] = dict(reversed(list(rule.items())))
    assert list(reordered["groups"][0]["rules"][0]) != list(
        SIMPLE_ALERT_RULES["groups"][0]["rules"][0]
    )

    assert _encode_alert_rules(reordered, encoding) == _encode_alert_rules(
        SIMPLE_ALERT_RULES, encoding
    )

