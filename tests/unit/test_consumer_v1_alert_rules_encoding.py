# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for negotiated alert_rules compression on the consumer (`ConsumerBase`) side.

`LokiPushApiConsumer`, `LogProxyConsumer`, and `LogForwarder` all share the alert
rules handling in `ConsumerBase._handle_alert_rules`, so exercising it through
`LokiPushApiConsumer` covers all three.
"""

import dataclasses
import json
import lzma
from base64 import b64decode
from pathlib import Path

import pytest
from charms.loki_k8s.v1.loki_push_api import (
    ALERT_RULES_ENCODINGS_KEY,
    ALERT_RULES_KEY,
    JSON_ENCODING,
    LZMA_ENCODING,
    LokiPushApiConsumer,
    _best_alert_rules_encoding,
)
from ops.charm import CharmBase
from ops.testing import Context
from scenario import Relation, State

FAKE_CONSUMER_META = {
    "name": "fake-consumer",
    "requires": {"logging": {"interface": "loki_push_api"}},
}

ALERT_RULE_YAML = """
alert: HighPercentageError
expr: |
  sum(rate({%%juju_topology%%} |= "error" [5m])) by (job)
for: 10m
labels:
    severity: page
annotations:
    summary: High request latency
"""


def _make_consumer_charm(rules_path: Path):
    class FakeConsumerCharm(CharmBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self.loki_consumer = LokiPushApiConsumer(self, alert_rules_path=str(rules_path))

    return FakeConsumerCharm


@pytest.fixture
def consumer_context(tmp_path):
    (tmp_path / "my_alert.rule").write_text(ALERT_RULE_YAML)
    return Context(_make_consumer_charm(tmp_path), meta=FAKE_CONSUMER_META)


def _decode(raw: str) -> dict:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = raw
    if isinstance(decoded, str):
        decoded = json.loads(lzma.decompress(b64decode(decoded)))
    return decoded


@pytest.mark.parametrize(
    "remote_app_databag, expected",
    [
        pytest.param(None, JSON_ENCODING, id="unreadable_databag"),
        pytest.param({}, JSON_ENCODING, id="no_advertisement"),
        pytest.param({ALERT_RULES_ENCODINGS_KEY: "[]"}, JSON_ENCODING, id="nothing_advertised"),
        pytest.param(
            {ALERT_RULES_ENCODINGS_KEY: json.dumps([JSON_ENCODING])},
            JSON_ENCODING,
            id="json_only",
        ),
        pytest.param(
            {ALERT_RULES_ENCODINGS_KEY: json.dumps(["brotli"])},
            JSON_ENCODING,
            id="unknown_encoding",
        ),
        pytest.param(
            {ALERT_RULES_ENCODINGS_KEY: "not json"},
            JSON_ENCODING,
            id="malformed_advertisement",
        ),
        pytest.param(
            {ALERT_RULES_ENCODINGS_KEY: json.dumps({"lzma": True})},
            JSON_ENCODING,
            id="not_a_list",
        ),
        pytest.param(
            {ALERT_RULES_ENCODINGS_KEY: json.dumps([LZMA_ENCODING, JSON_ENCODING])},
            LZMA_ENCODING,
            id="lzma_advertised",
        ),
        pytest.param(
            {ALERT_RULES_ENCODINGS_KEY: json.dumps(["brotli", LZMA_ENCODING])},
            LZMA_ENCODING,
            id="lzma_among_unknown_encodings",
        ),
    ],
)
def test_encoding_negotiation(remote_app_databag, expected):
    """Matrix of inputs for `_best_alert_rules_encoding`, exercised directly."""
    assert _best_alert_rules_encoding(remote_app_databag) == expected


def test_consumer_compresses_when_provider_advertises_lzma(consumer_context):
    """The consumer writes an LZMA-compressed payload when the provider supports it."""
    logging_relation = Relation(
        "logging",
        remote_app_name="loki",
        remote_app_data={ALERT_RULES_ENCODINGS_KEY: json.dumps([LZMA_ENCODING, JSON_ENCODING])},
    )
    state = State(leader=True, relations=[logging_relation])

    state_out = consumer_context.run(
        consumer_context.on.relation_joined(logging_relation), state
    )

    relation = state_out.get_relation(logging_relation.id)
    raw = relation.local_app_data[ALERT_RULES_KEY]

    # Not plain JSON: it must be a compressed, base64-encoded payload.
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)

    decoded = _decode(raw)
    assert decoded["groups"][0]["rules"][0]["alert"] == "HighPercentageError"


def test_consumer_falls_back_to_json_for_legacy_provider(consumer_context):
    """The consumer writes plain JSON when the provider advertises nothing."""
    logging_relation = Relation("logging", remote_app_name="loki")
    state = State(leader=True, relations=[logging_relation])

    state_out = consumer_context.run(
        consumer_context.on.relation_joined(logging_relation), state
    )

    relation = state_out.get_relation(logging_relation.id)
    raw = relation.local_app_data[ALERT_RULES_KEY]

    # Plain JSON: readable directly, no compression.
    decoded = json.loads(raw)
    assert decoded["groups"][0]["rules"][0]["alert"] == "HighPercentageError"


def test_consumer_writes_plain_json_when_provider_only_advertises_json(consumer_context):
    """The consumer writes plain JSON when the provider only advertises `json`."""
    logging_relation = Relation(
        "logging",
        remote_app_name="loki",
        remote_app_data={ALERT_RULES_ENCODINGS_KEY: json.dumps([JSON_ENCODING])},
    )
    state = State(leader=True, relations=[logging_relation])

    state_out = consumer_context.run(
        consumer_context.on.relation_joined(logging_relation), state
    )

    relation = state_out.get_relation(logging_relation.id)
    raw = relation.local_app_data[ALERT_RULES_KEY]

    decoded = json.loads(raw)
    assert decoded["groups"][0]["rules"][0]["alert"] == "HighPercentageError"


def test_consumer_re_encodes_on_relation_changed_once_provider_advertises_lzma(
    consumer_context,
):
    """A consumer that starts seeing lzma re-encodes on relation-changed.

    Encodings are only known once the provider has had a chance to advertise them,
    which may happen after the relation was first established.
    """
    logging_relation = Relation("logging", remote_app_name="loki")
    state = State(leader=True, relations=[logging_relation])

    # First contact: legacy provider, plain JSON.
    state_mid = consumer_context.run(
        consumer_context.on.relation_joined(logging_relation), state
    )
    relation_mid = state_mid.get_relation(logging_relation.id)
    assert json.loads(relation_mid.local_app_data[ALERT_RULES_KEY])

    # Provider upgrades and starts advertising lzma; consumer sees relation-changed.
    relation_upgraded = dataclasses.replace(
        relation_mid,
        remote_app_data={
            **relation_mid.remote_app_data,
            ALERT_RULES_ENCODINGS_KEY: json.dumps([LZMA_ENCODING, JSON_ENCODING]),
        },
    )
    state_out = consumer_context.run(
        consumer_context.on.relation_changed(relation_upgraded),
        dataclasses.replace(state_mid, relations=[relation_upgraded]),
    )

    relation_out = state_out.get_relation(logging_relation.id)
    raw = relation_out.local_app_data[ALERT_RULES_KEY]
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    decoded = _decode(raw)
    assert decoded["groups"][0]["rules"][0]["alert"] == "HighPercentageError"


def test_consumer_republishing_is_idempotent(consumer_context):
    """Re-encoding the same rules on a subsequent hook produces byte-identical output.

    Juju only emits relation-changed on the other side if the databag value actually
    changes. If encoding weren't deterministic/idempotent, every unrelated hook could
    cause a spurious relation-changed loop between the consumer and provider.
    """
    logging_relation = Relation(
        "logging",
        remote_app_name="loki",
        remote_app_data={ALERT_RULES_ENCODINGS_KEY: json.dumps([LZMA_ENCODING, JSON_ENCODING])},
    )
    state = State(leader=True, relations=[logging_relation])

    state_mid = consumer_context.run(
        consumer_context.on.relation_changed(logging_relation), state
    )
    published = state_mid.get_relation(logging_relation.id).local_app_data[ALERT_RULES_KEY]

    # A second, unrelated relation-changed (e.g. the provider only updated its endpoint,
    # not its advertised encodings) re-runs the same encode step.
    state_out = consumer_context.run(
        consumer_context.on.relation_changed(state_mid.get_relation(logging_relation.id)),
        state_mid,
    )
    republished = state_out.get_relation(logging_relation.id).local_app_data[ALERT_RULES_KEY]

    assert republished == published
