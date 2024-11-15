import logging
from unittest.mock import patch

import ops.pebble
import pytest
from ops.testing import Container, Exec, State


@pytest.fixture
def loki_emitter():
    with patch("charms.loki_k8s.v0.charm_logging.LokiHandler.emit") as h:
        yield h


def test_no_endpoints_on_loki_not_ready(context, loki_emitter):
    state = State(
        containers=[
            Container(
                "loki",
                can_connect=True,
                layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
                service_statuses={"loki": ops.pebble.ServiceStatus.INACTIVE},
                execs={Exec(["update-ca-certificates", "--fresh"], return_code=0)},
            )
        ]
    )

    with context(context.on.update_status(), state) as mgr:
        charm = mgr.charm
        assert charm._charm_logging_endpoints == []
        logging.getLogger("foo").debug("bar")

    loki_emitter.assert_not_called()


def test_endpoints_on_loki_ready(context, loki_emitter):
    state = State(
        containers=[
            Container(
                "loki",
                can_connect=True,
                layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
                service_statuses={"loki": ops.pebble.ServiceStatus.ACTIVE},
                execs={Exec(["update-ca-certificates", "--fresh"], return_code=0)},
            )
        ]
    )

    with context(context.on.update_status(), state) as mgr:
        charm = mgr.charm
        assert charm._charm_logging_endpoints == ["http://localhost:3100/loki/api/v1/push"]
        logging.getLogger("foo").debug("bar")

    loki_emitter.assert_called()

    for call in loki_emitter.call_args_list:
        record = call.args[0]
        if record.filename == __name__ + ".py":  # log emitted by this module
            assert record.msg == "bar"
            assert record.name == "foo"


@patch("charm.LokiOperatorCharm._charm_logging_ca_cert", new_callable=lambda *_: True)
def test_endpoints_on_loki_ready_tls(_, context, loki_emitter):
    state = State(
        containers=[
            Container(
                "loki",
                can_connect=True,
                layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
                service_statuses={"loki": ops.pebble.ServiceStatus.ACTIVE},
                execs={Exec(["update-ca-certificates", "--fresh"], return_code=0)},
            )
        ]
    )

    with context(context.on.update_status(), state) as mgr:
        charm = mgr.charm
        assert charm._charm_logging_endpoints == ["https://localhost:3100/loki/api/v1/push"]
        logging.getLogger("foo").debug("bar")

    loki_emitter.assert_called()

    for call in loki_emitter.call_args_list:
        record = call.args[0]
        if record.filename == __name__ + ".py":  # log emitted by this module
            assert record.msg == "bar"
            assert record.name == "foo"
