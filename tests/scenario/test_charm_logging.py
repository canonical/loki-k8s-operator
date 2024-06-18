import logging
from unittest.mock import patch

import ops.pebble
import pytest
import scenario


@pytest.fixture
def loki_emitter():
    with patch("charms.loki_k8s.v0.charm_logging.LokiHandler.emit") as h:
        yield h


def test_no_endpoints_on_loki_not_ready(context, loki_emitter):
    state = scenario.State(
        containers=[
            scenario.Container(
                "loki",
                can_connect=True,
                layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
                service_status={"loki": ops.pebble.ServiceStatus.INACTIVE},
                exec_mock={("update-ca-certificates", "--fresh"): scenario.ExecOutput()},
            )
        ]
    )

    with context.manager("update-status", state) as mgr:
        charm = mgr.charm
        assert charm.logging_endpoints == []
        logging.getLogger("foo").debug("bar")

    loki_emitter.assert_not_called()


def test_endpoints_on_loki_ready(context, loki_emitter):
    state = scenario.State(
        containers=[
            scenario.Container(
                "loki",
                can_connect=True,
                layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
                service_status={"loki": ops.pebble.ServiceStatus.ACTIVE},
                exec_mock={("update-ca-certificates", "--fresh"): scenario.ExecOutput()},
            )
        ]
    )

    with context.manager("update-status", state) as mgr:
        charm = mgr.charm
        assert charm.logging_endpoints == ["http://localhost:3100/loki/api/v1/push"]
        logging.getLogger("foo").debug("bar")

    loki_emitter.assert_called()

    for call in loki_emitter.call_args_list:
        record = call.args[0]
        if record.filename == __name__ + ".py":  # log emitted by this module
            assert record.msg == "bar"
            assert record.name == "foo"


@patch("charm.LokiOperatorCharm.server_ca_cert_path", new_callable=lambda *_: True)
def test_endpoints_on_loki_ready_tls(_, context, loki_emitter):
    state = scenario.State(
        containers=[
            scenario.Container(
                "loki",
                can_connect=True,
                layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
                service_status={"loki": ops.pebble.ServiceStatus.ACTIVE},
                exec_mock={("update-ca-certificates", "--fresh"): scenario.ExecOutput()},
            )
        ]
    )

    with context.manager("update-status", state) as mgr:
        charm = mgr.charm
        assert charm.logging_endpoints == ["https://localhost:3100/loki/api/v1/push"]
        logging.getLogger("foo").debug("bar")

    loki_emitter.assert_called()

    for call in loki_emitter.call_args_list:
        record = call.args[0]
        if record.filename == __name__ + ".py":  # log emitted by this module
            assert record.msg == "bar"
            assert record.name == "foo"
