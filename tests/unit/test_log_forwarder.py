# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import pytest
from charms.loki_k8s.v1.loki_push_api import LogForwarder, _PebbleLogClient
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
                },
            },
        }
        actual_layer_config = _PebbleLogClient._build_log_targets(
            expected_endpoints, charm.log_forwarder.topology, True
        )
        assert expected_layer_config == actual_layer_config
