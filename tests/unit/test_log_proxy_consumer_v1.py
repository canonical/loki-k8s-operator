# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Expected behaviour tests for https://github.com/canonical/loki-k8s-operator/issues/659.

After workload container churn, LogProxyConsumer can be left in a state where the
pebble plan references /opt/promtail/promtail-static-amd64 but the binary is gone
(it lives on ephemeral storage and is pushed at runtime by the charm).

These tests encode the desired post-fix behaviour:

1. ``_setup_promtail`` must be atomic: if obtaining the promtail binary fails,
   the pebble layer must not reference a service whose executable is absent.
2. ``_on_relation_changed`` must not trust the pebble plan alone: when the plan
   references promtail but the binary is missing, it must fall back to
   re-provisioning instead of calling ``container.restart()`` unconditionally
   (real Pebble fails that start with ``fork/exec ... no such file or
   directory``, wedging the unit in hook error forever).
3. After a successful provisioning, subsequent relation-changed events must
   never wedge the unit, even when the workload container lost its ephemeral
   filesystem in between (pod/container churn).

The ``pebble_restart_checks_binary`` fixture (defined in
``tests/unit/conftest.py``) teaches the simulated Pebble what real Pebble does:
reject service starts whose executable is absent.
"""

import json
import platform
from hashlib import sha256
from unittest.mock import patch
from urllib.error import URLError

import pytest
from charms.loki_k8s.v1.loki_push_api import LogProxyConsumer
from helpers import pebble_change_error
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.model import Container as OpsContainer
from ops.pebble import Layer, ServiceStatus
from ops.testing import Context
from scenario import Container, Model, Relation, State

WORKLOAD_BINARY_PATH = "/opt/promtail/promtail-static-amd64"
FAKE_BINARY_CONTENT = b"#!fake-promtail-binary"

META = {
    "name": "consumer-k8s",
    "requires": {"log-proxy": {"interface": "loki_push_api", "optional": True}},
    "containers": {"app": {"resource": "app-image"}},
}


class LogProxyConsumerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(promtail_digest_errors=0, endpoint_joined_events=0)
        self.log_proxy = LogProxyConsumer(
            charm=self,
            logs_scheme={"app": {"log-files": ["/var/log/app/*.log"]}},
        )
        self.framework.observe(
            self.log_proxy.on.promtail_digest_error, self._register_digest_error
        )
        self.framework.observe(
            self.log_proxy.on.log_proxy_endpoint_joined, self._register_endpoint_joined
        )

    def _register_digest_error(self, _):
        self._stored.promtail_digest_errors += 1

    def _register_endpoint_joined(self, _):
        self._stored.endpoint_joined_events += 1


@pytest.fixture
def app_container():
    return Container("app", can_connect=True)


@pytest.fixture
def consumer_context():
    return Context(LogProxyConsumerCharm, meta=META)


@pytest.fixture
def log_proxy_relation():
    """A log-proxy relation as the Loki provider side would have populated it."""
    digest = sha256(FAKE_BINARY_CONTENT).hexdigest()
    arch = "amd64" if platform.machine() == "x86_64" else platform.machine()
    return Relation(
        endpoint="log-proxy",
        remote_app_name="loki",
        remote_app_data={
            "promtail_binary_zip_url": json.dumps(
                {
                    arch: {
                        "filename": "promtail-static-amd64",
                        "zipsha": digest,
                        "binsha": digest,
                        "url": "http://promtail.invalid/promtail.zip",
                    }
                }
            )
        },
        remote_units_data={
            0: {"endpoint": json.dumps({"url": "http://loki:3100/loki/api/v1/push"})}
        },
    )


def _base_state(container: Container, relation: Relation) -> State:
    return State(
        leader=True,
        containers=[container],
        relations=[relation],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )



def _plan_service_names(container_state: Container) -> set:
    services = {}
    for layer in container_state.layers.values():
        services.update(layer.services)
    return set(services)


def _wedged_container() -> Container:
    """Container in the inconsistent state from the issue: layer added, binary gone."""
    return Container(
        "app",
        can_connect=True,
        layers={
            "app": Layer(
                {
                    "summary": "promtail layer",
                    "services": {
                        "promtail": {
                            "override": "replace",
                            "summary": "promtail",
                            "command": (
                                f"{WORKLOAD_BINARY_PATH} "
                                "-config.file=/etc/promtail/promtail_config.yaml"
                            ),
                            "startup": "disabled",
                        }
                    },
                }
            )
        },
    )


def test_binary_not_advertised_for_this_architecture_does_not_crash_hook(
    consumer_context,
    app_container,
    pebble_restart_checks_binary,
):
    """A spec without our architecture must be reported, not raise KeyError."""
    # GIVEN Loki advertises a promtail binary only for an architecture we are not running on
    foreign_arch_relation = Relation(
        endpoint="log-proxy",
        remote_app_name="loki",
        remote_app_data={
            "promtail_binary_zip_url": json.dumps(
                {"s390x": {"filename": "promtail-static-s390x", "zipsha": "x", "binsha": "y"}}
            )
        },
        remote_units_data={
            0: {"endpoint": json.dumps({"url": "http://loki:3100/loki/api/v1/push"})}
        },
    )
    state = _base_state(app_container, foreign_arch_relation)

    # WHEN the log-proxy relation changes
    state_out = consumer_context.run(
        consumer_context.on.relation_changed(foreign_arch_relation, remote_unit=0), state
    )

    # THEN the hook survives, no promtail service is registered, and the operator is told why
    assert "promtail" not in _plan_service_names(state_out.get_container("app"))
    with consumer_context(consumer_context.on.update_status(), state_out) as mgr:
        assert mgr.charm._stored.promtail_digest_errors == 1


def test_failed_binary_download_does_not_add_pebble_layer(
    consumer_context,
    app_container,
    log_proxy_relation,
    pebble_restart_checks_binary,
    tmp_path,
):
    """Provisioning must be atomic: no layer referencing a binary that isn't there."""
    # GIVEN no promtail binary is cached in the charm container
    state = _base_state(app_container, log_proxy_relation)
    with (
        patch("charms.loki_k8s.v1.loki_push_api.BINARY_DIR", str(tmp_path)),
        patch(
            "charms.loki_k8s.v1.loki_push_api.LogProxyConsumer."
            "_download_and_push_promtail_to_workload"
        ) as mock_download,
    ):
        # AND downloading it fails (e.g. no juju proxy configured)
        mock_download.side_effect = URLError(reason="[Errno 110] Connection timed out")

        # WHEN the log-proxy relation changes and provisioning is attempted
        state_out = consumer_context.run(
            consumer_context.on.relation_changed(log_proxy_relation, remote_unit=0), state
        )

    # THEN no promtail service is left pointing at the missing binary
    assert "promtail" not in _plan_service_names(state_out.get_container("app"))
    # AND the failure is surfaced once, without erroring the hook
    with consumer_context(consumer_context.on.update_status(), state_out) as mgr:
        assert mgr.charm._stored.promtail_digest_errors == 1


def test_relation_changed_heals_wedged_container_by_reprovisioning(
    consumer_context,
    log_proxy_relation,
    pebble_restart_checks_binary,
    tmp_path,
):
    """A wedged unit must recover on relation-changed instead of erroring forever."""
    # GIVEN a container wedged as in the issue: promtail is in the pebble plan
    # but its binary is gone from the ephemeral filesystem
    state = _base_state(_wedged_container(), log_proxy_relation)
    # AND the promtail binary is available again (e.g. the network recovered)
    (tmp_path / "promtail-static-amd64").write_bytes(FAKE_BINARY_CONTENT)

    with patch("charms.loki_k8s.v1.loki_push_api.BINARY_DIR", str(tmp_path)):
        # WHEN the log-proxy relation changes
        state_out = consumer_context.run(
            consumer_context.on.relation_changed(log_proxy_relation, remote_unit=0), state
        )

    # THEN promtail is re-provisioned and running, with nothing reported as broken
    container_out = state_out.get_container("app")
    assert container_out.service_statuses["promtail"] == ServiceStatus.ACTIVE
    with consumer_context(consumer_context.on.update_status(), state_out) as mgr:
        assert mgr.charm._stored.promtail_digest_errors == 0


def test_second_relation_changed_after_churn_does_not_wedge_unit(
    consumer_context,
    app_container,
    log_proxy_relation,
    pebble_restart_checks_binary,
    tmp_path,
):
    """Later relation-changed events must never wedge the unit, even after churn."""
    # GIVEN the promtail binary is cached in the charm container
    (tmp_path / "promtail-static-amd64").write_bytes(FAKE_BINARY_CONTENT)
    state = _base_state(app_container, log_proxy_relation)

    with patch("charms.loki_k8s.v1.loki_push_api.BINARY_DIR", str(tmp_path)):
        # AND a first relation-changed provisioned and started promtail
        state_out = consumer_context.run(
            consumer_context.on.relation_changed(log_proxy_relation, remote_unit=0), state
        )
        assert state_out.get_container("app").service_statuses["promtail"] == (
            ServiceStatus.ACTIVE
        )

        # WHEN a second relation-changed arrives after the workload container lost its
        # ephemeral filesystem (scenario does not carry files pushed in a previous run,
        # which mirrors exactly what Kubernetes does on pod/container churn)
        healthy_relation = state_out.get_relations("log-proxy")[0]
        state_out2 = consumer_context.run(
            consumer_context.on.relation_changed(healthy_relation, remote_unit=0),
            state_out,
        )

    # THEN the unit does not wedge: promtail is set up again and keeps running
    assert (
        state_out2.get_container("app").service_statuses["promtail"] == ServiceStatus.ACTIVE
    )


def test_already_set_up_container_restarts_promtail_and_reports_endpoint_joined(
    consumer_context,
    log_proxy_relation,
):
    """Fast path: promtail already set up, so relation-changed only restarts it."""
    # GIVEN promtail is already set up: the service is in the plan and the binary is installed
    state = _base_state(_wedged_container(), log_proxy_relation)

    with patch(
        "charms.loki_k8s.v1.loki_push_api.LogProxyConsumer._is_promtail_installed",
        return_value=True,
    ):
        # WHEN the log-proxy relation changes
        state_out = consumer_context.run(
            consumer_context.on.relation_changed(log_proxy_relation, remote_unit=0), state
        )

    # THEN promtail is restarted and the endpoint is reported as joined, with no errors
    assert state_out.get_container("app").service_statuses["promtail"] == ServiceStatus.ACTIVE
    with consumer_context(consumer_context.on.update_status(), state_out) as mgr:
        assert mgr.charm._stored.endpoint_joined_events == 1
        assert mgr.charm._stored.promtail_digest_errors == 0


def test_restart_failure_on_set_up_container_does_not_error_the_unit(
    consumer_context,
    log_proxy_relation,
):
    """A Pebble failure while restarting promtail must be reported, not crash the hook."""
    # GIVEN promtail is already set up in the container
    state = _base_state(_wedged_container(), log_proxy_relation)
    # AND Pebble refuses to restart it, as it does while a container is terminating
    restart_error = pebble_change_error(
        'cannot perform the following tasks:\n- Start service "promtail" '
        "(cannot start service while terminating)"
    )

    with (
        patch(
            "charms.loki_k8s.v1.loki_push_api.LogProxyConsumer._is_promtail_installed",
            return_value=True,
        ),
        patch.object(OpsContainer, "restart", side_effect=restart_error),
    ):
        # WHEN the log-proxy relation changes
        state_out = consumer_context.run(
            consumer_context.on.relation_changed(log_proxy_relation, remote_unit=0), state
        )

    # THEN the failure is surfaced as a digest error instead of erroring the hook
    with consumer_context(consumer_context.on.update_status(), state_out) as mgr:
        assert mgr.charm._stored.promtail_digest_errors == 1
        assert mgr.charm._stored.endpoint_joined_events == 0
