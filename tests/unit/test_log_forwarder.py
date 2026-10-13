# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import pytest
from charms.loki_k8s.v1.loki_push_api import LogForwarder, _PebbleLogClient
from ops import pebble
from ops.charm import CharmBase
from ops.testing import Context
from scenario import Container, Relation, State

FAKE_CHARM_META = {
    "name": "fake-charm",
    "containers": {"consumer": {"resource": "consumer-image"}},
    "requires": {"logging": {"interface": "loki_push_api"}},
}


class FakeCharm(CharmBase):
    """Container charm for forwarding logs using the logforwarder class."""

    def __init__(self, *args):
        super().__init__(*args)
        self.log_forwarder = LogForwarder(self)


@pytest.fixture
def log_forwarder_context():
    return Context(FakeCharm, meta=FAKE_CHARM_META)


def test_handle_logging_with_relation_lifecycle(log_forwarder_context):
    """Test that log forwarding handles relation lifecycle correctly."""
    # Create relation with 2 loki units
    logging_relation = Relation(
        "logging",
        remote_app_name="loki",
        remote_units_data={
            0: {"endpoint": json.dumps({"url": "http://loki-0:3100/loki/api/v1/push"})},
            1: {"endpoint": json.dumps({"url": "http://loki-1:3100/loki/api/v1/push"})},
        },
    )

    # Add consumer container
    consumer_container = Container("consumer", can_connect=True)

    state = State(relations=[logging_relation], containers=[consumer_container], planned_units=1)

    with log_forwarder_context(
        log_forwarder_context.on.relation_changed(logging_relation), state
    ) as mgr:
        charm = mgr.charm
        relation_obj = charm.model.relations["logging"][0]

        expected_endpoints = {
            "loki/0": "http://loki-0:3100/loki/api/v1/push",
            "loki/1": "http://loki-1:3100/loki/api/v1/push",
        }
        assert charm.log_forwarder._fetch_endpoints(relation_obj) == expected_endpoints

        expected_layer_config = {
            "loki/0": {
                "override": "replace",
                "type": "loki",
                "location": "http://loki-0:3100/loki/api/v1/push",
                "services": ["all"],
                "labels": {
                    "product": "Juju",
                    "charm": charm.log_forwarder.topology._charm_name,
                    "juju_model": charm.log_forwarder.topology._model,
                    "juju_model_uuid": charm.log_forwarder.topology._model_uuid,
                    "juju_application": charm.log_forwarder.topology._application,
                    "juju_unit": charm.log_forwarder.topology._unit,
                    "job": f"juju_{charm.log_forwarder.topology.identifier}",
                },
            },
            "loki/1": {
                "override": "replace",
                "type": "loki",
                "location": "http://loki-1:3100/loki/api/v1/push",
                "services": ["all"],
                "labels": {
                    "product": "Juju",
                    "charm": charm.log_forwarder.topology._charm_name,
                    "juju_model": charm.log_forwarder.topology._model,
                    "juju_model_uuid": charm.log_forwarder.topology._model_uuid,
                    "juju_application": charm.log_forwarder.topology._application,
                    "juju_unit": charm.log_forwarder.topology._unit,
                    "job": f"juju_{charm.log_forwarder.topology.identifier}",
                },
            },
        }
        actual_layer_config = _PebbleLogClient._build_log_targets(
            expected_endpoints, charm.log_forwarder.topology, True
        )
        assert expected_layer_config == actual_layer_config


def test_relation_broken_disables_log_target(log_forwarder_context):
    """Removing the last Loki relation disables the stale log target.

    ``_update_logging`` used to return early when no endpoints remained, leaving the
    target of a removed relation enabled so that Pebble kept retrying the old endpoint.
    """
    # GIVEN a consumer already forwarding to a Loki endpoint
    consumer_container = Container(
        "consumer",
        can_connect=True,
        layers={
            "consumer-log-forwarding": pebble.Layer(
                {
                    "log-targets": {
                        "loki/0": {
                            "override": "replace",
                            "type": "loki",
                            "location": "http://loki-0:3100/loki/api/v1/push",
                            "services": ["all"],
                        }
                    }
                }
            )
        },
    )
    # AND the relation has been removed, so it carries no endpoints
    broken_relation = Relation("logging", remote_app_name="loki")
    state = State(relations=[broken_relation], containers=[consumer_container], planned_units=1)

    # WHEN relation-broken fires
    with log_forwarder_context(
        log_forwarder_context.on.relation_broken(broken_relation), state
    ) as mgr:
        state_out = mgr.run()

    # THEN the stale target is disabled
    layer = state_out.get_container("consumer").layers["consumer-log-forwarding"]
    assert layer.to_dict()["log-targets"]["loki/0"]["services"] == ["-all"]
