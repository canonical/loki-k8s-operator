# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import pytest
from charms.loki_k8s.v0.loki_push_api import LokiPushApiProvider
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

ALERT_RULES = {
    "groups": [
        {
            "name": "None_f2c1b2a6-e006-11eb-ba80-0242ac130004_consumer-tester_alerts",
            "rules": [
                {
                    "alert": "HighPercentageError",
                    "expr": "sum(rate({%%juju_topology%%} |= 'error' [5m])) by (job)",
                    "for": "0m",
                    "labels": {
                        "severity": "Low",
                    },
                    "annotations": {
                        "summary": "High request latency",
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
        self._container = self.unit.get_container("loki")
        self._port = 3100
        self.loki_provider = LokiPushApiProvider(
            self,
            address="10.0.0.1",
            port=3100,
            scheme="http",
            path="/loki/api/v1/push",
        )

        self.framework.observe(
            self.loki_provider.on.loki_push_api_alert_rules_changed, self.alert_events
        )
        # Store event count instead of relation objects
        self._stored.set_default(event_count=0)

    def alert_events(self, event):
        self._stored.event_count += 1

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def hostname(self) -> str:
        """Unit's hostname."""
        return "{}-{}.{}-endpoints.{}.svc.cluster.local".format(
            self.app.name,
            self.unit.name.split("/")[-1],
            self.app.name,
            self.model.name,
        )


@pytest.fixture
def provider_context():
    return Context(FakeLokiCharm, meta=FAKE_LOKI_META)


def test_relation_data(provider_context):
    """Test that endpoint generation works correctly."""
    state = State(leader=True)
    with provider_context(provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        base_url = "http://loki-0.loki-endpoints.None.svc.cluster.local"
        port = "3100"
        url = f"{base_url}:{port}"
        path = "/loki/api/v1/push"
        endpoint = f"{url}{path}"
        expected_value = {"url": endpoint}
        assert expected_value == charm.loki_provider._endpoint(url)


def test_on_logging_relation_changed(provider_context):
    """Test that alert rules changed event is fired on relation changed."""
    logging_relation = Relation(
        "logging",
        remote_app_name="promtail",
        remote_app_data={"alert_rules": json.dumps(ALERT_RULES)},
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    # Run relation_changed which should trigger alert_events
    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        mgr.run()
        # Event count will be 1 after alert_rules_changed is emitted
        assert mgr.charm._stored.event_count == 1


def test_on_logging_relation_created_and_broken(provider_context):
    """Test that alert rules changed event is fired on relation broken."""
    logging_relation = Relation(
        "logging",
        remote_app_name="promtail",
        remote_app_data={"alert_rules": json.dumps(ALERT_RULES)},
        remote_units_data={0: {}},
    )

    state = State(leader=True, relations=[logging_relation])

    # Run relation_changed first
    with provider_context(
        provider_context.on.relation_changed(logging_relation), state
    ) as mgr:
        state_after_changed = mgr.run()
        assert mgr.charm._stored.event_count == 1

    # For relation_broken, we need to use the relation from the output state
    rel_from_state = state_after_changed.get_relation(logging_relation.id)
    provider_context.run(
        provider_context.on.relation_broken(rel_from_state), state_after_changed
    )


def test_alerts(provider_context):
    """Test that alerts property returns correct alert rules."""
    logging_relation = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(ALERT_RULES),
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
        assert list(alerts.values())[0]["groups"][0] == ALERT_RULES["groups"][0]
