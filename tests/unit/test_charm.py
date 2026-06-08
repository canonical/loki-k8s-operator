# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
from dataclasses import replace
from http.client import HTTPMessage
from io import BytesIO
from unittest.mock import Mock, PropertyMock, patch
from urllib.error import HTTPError, URLError

import ops
import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Context
from scenario import Container, Exec, Relation, State

from charm import LOKI_CONFIG as LOKI_CONFIG_PATH
from charm import LokiOperatorCharm

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
                    "expr": 'sum(rate({job="app"} |= "error" [5m])) by (job)',
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


def tautology(*_, **__) -> bool:
    return True


@pytest.fixture
def loki_charm():
    with patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace=PropertyMock("test-namespace"),
        _patch=PropertyMock(tautology),
        is_ready=PropertyMock(tautology),
    ):
        with patch("socket.getfqdn", new=lambda *args: "fqdn"):
            with patch("lightkube.core.client.GenericSyncClient"):
                yield LokiOperatorCharm


@pytest.fixture
def ctx(loki_charm):
    return Context(loki_charm)


@pytest.fixture
def loki_container():
    """Loki container with all required execs for version check."""
    return Container(
        "loki",
        can_connect=True,
        execs={
            Exec(["update-ca-certificates", "--fresh"], return_code=0),
            Exec(["/usr/bin/loki", "-version"], return_code=0, stdout="loki, version 3.14159"),
        },
        layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
        service_statuses={"loki": ops.pebble.ServiceStatus.INACTIVE},
    )


@pytest.fixture
def loki_container_cannot_connect():
    return Container(
        "loki",
        can_connect=False,
        execs={
            Exec(["update-ca-certificates", "--fresh"], return_code=0),
            Exec(["/usr/bin/loki", "-version"], return_code=0, stdout="loki, version 3.14159"),
        },
        layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
        service_statuses={"loki": ops.pebble.ServiceStatus.INACTIVE},
    )


# --- TestCharm ---


def test_alerting_config(ctx, loki_container):
    """Test _alerting_config method returns correct alertmanager URLs."""
    state = State(leader=True, containers=[loki_container])

    with ctx(ctx.on.start(), state) as mgr:
        charm = mgr.charm
        # Mock the alertmanager_consumer
        charm.alertmanager_consumer = Mock()
        mock_cluster = {"http://10.1.2.52", "http://10.1.3.52"}
        charm.alertmanager_consumer.get_cluster_info.return_value = mock_cluster
        result = charm._alerting_config()
        assert set(result.split(",")) == mock_cluster

        # Test empty cluster
        charm.alertmanager_consumer.get_cluster_info.return_value = set()
        assert charm._alerting_config() == ""


def test_on_config_cannot_connect(ctx, loki_container_cannot_connect):
    """Test that charm goes to Maintenance when cannot connect to container."""
    state = State(leader=True, containers=[loki_container_cannot_connect])

    with patch("config_builder.ConfigBuilder.build") as mock_build:
        mock_build.return_value = {}
        state_out = ctx.run(ctx.on.config_changed(), state)

    # When can't connect, charm stays in Maintenance (exact message may vary)
    assert isinstance(state_out.unit_status, MaintenanceStatus)


def test_on_config_can_connect(ctx, loki_container):
    """Test that charm goes to Active when connected to container."""
    state = State(leader=True, containers=[loki_container])

    with patch("config_builder.ConfigBuilder.build") as mock_build, patch.object(
        LokiOperatorCharm, "_update_cert"
    ):
        mock_build.return_value = {}
        state_out = ctx.run(ctx.on.config_changed(), state)

    assert state_out.unit_status == ActiveStatus()


# --- TestConfigFile ---


def test_relating_over_alertmanager_updates_config_with_ip_addresses(ctx, loki_container):
    """Scenario: The charm is related to alertmanager."""
    # GIVEN no alertmanager units initially
    state_in = State(leader=True, containers=[loki_container])

    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=True), patch.object(
        LokiOperatorCharm, "_update_cert"
    ):
        # Run to get initial config
        state_with_config = ctx.run(ctx.on.config_changed(), state_in)

        # Check initial state - alertmanager_url should be empty
        fs = state_with_config.get_container("loki").get_filesystem(ctx)
        config = yaml.safe_load((fs / LOKI_CONFIG_PATH.lstrip("/")).read_text())
        assert config["ruler"]["alertmanager_url"] == ""

        # WHEN alertmanager units join
        alertmanager_rel = Relation(
            "alertmanager",
            remote_app_name="alertmanager-app",
            remote_units_data={
                0: {"public_address": "10.0.0.1"},
                1: {"public_address": "10.0.0.2"},
            },
        )
        state_with_am = replace(state_with_config, relations=frozenset([alertmanager_rel]))

        state_after_am = ctx.run(ctx.on.relation_changed(alertmanager_rel), state_with_am)

        # THEN the alertmanager_url property has their ip addresses
        fs2 = state_after_am.get_container("loki").get_filesystem(ctx)
        config2 = yaml.safe_load((fs2 / LOKI_CONFIG_PATH.lstrip("/")).read_text())
        assert set(config2["ruler"]["alertmanager_url"].split(",")) == {
            "http://10.0.0.1",
            "http://10.0.0.2",
        }

        # WHEN the relation is broken
        rel_from_state = state_after_am.get_relation(alertmanager_rel.id)
        state_broken = ctx.run(ctx.on.relation_broken(rel_from_state), state_after_am)

        # THEN the alertmanager_url property is blank again
        fs3 = state_broken.get_container("loki").get_filesystem(ctx)
        config3 = yaml.safe_load((fs3 / LOKI_CONFIG_PATH.lstrip("/")).read_text())
        assert config3["ruler"]["alertmanager_url"] == ""


def test_instance_address_is_set_to_this_unit_ip(ctx, loki_container):
    """Test that instance_addr is set to fqdn."""
    state = State(leader=True, containers=[loki_container])

    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=True), patch.object(
        LokiOperatorCharm, "_update_cert"
    ):
        state_out = ctx.run(ctx.on.config_changed(), state)

        # THEN the instance_addr property has the fqdn
        fs = state_out.get_container("loki").get_filesystem(ctx)
        config = yaml.safe_load((fs / LOKI_CONFIG_PATH.lstrip("/")).read_text())
        assert config["common"]["ring"]["instance_addr"] == "fqdn"


# --- TestPebblePlan ---


def test_loki_starts_when_cluster_deployed_without_any_relations(ctx, loki_container):
    """Scenario: A loki cluster is deployed without any relations."""
    # Create logging relations
    logging_rels = [
        Relation(
            "logging",
            remote_app_name=f"consumer-app-{i}",
            remote_units_data={0: {}, 1: {}},
        )
        for i in range(3)
    ]

    state = State(leader=True, containers=[loki_container], relations=logging_rels)

    with patch.object(LokiOperatorCharm, "_update_cert"):
        state_out = ctx.run(ctx.on.pebble_ready(loki_container), state)

    # THEN a pebble service is created for this unit
    container = state_out.get_container("loki")
    plan = container.plan
    assert "loki" in plan.services

    # AND the command includes a config file
    command = plan.services["loki"].command
    assert "-config.file=" in command


# --- TestDelayedPebbleReady ---


def test_pebble_ready_changes_status_from_waiting_to_active(ctx, loki_container):
    """Scenario: a pebble-ready event is delayed."""
    # GIVEN charm started without pebble ready
    loki_not_ready = Container(
        "loki",
        can_connect=False,
        execs={
            Exec(["update-ca-certificates", "--fresh"], return_code=0),
            Exec(["/usr/bin/loki", "-version"], return_code=0, stdout="loki, version 3.14159"),
        },
    )
    state_waiting = State(leader=True, containers=[loki_not_ready])

    with patch("charm.LokiOperatorCharm._check_alert_rules", return_value=True), patch(
        "charm.LokiOperatorCharm._loki_version",
        new_callable=PropertyMock,
        return_value="3.14159",
    ), patch.object(LokiOperatorCharm, "_update_cert"):
        # Before pebble ready - charm should be in Maintenance
        state_before = ctx.run(ctx.on.config_changed(), state_waiting)
        assert isinstance(state_before.unit_status, MaintenanceStatus)

        # After pebble ready
        state_with_pebble = replace(state_before, containers=frozenset([loki_container]))
        state_after = ctx.run(ctx.on.pebble_ready(loki_container), state_with_pebble)
        assert state_after.unit_status == ActiveStatus()


# --- TestAppRelationData ---


def test_endpoint(ctx, loki_container):
    """Test that endpoint relation data is set correctly."""
    logging_rel = Relation(
        "logging",
        remote_app_name="consumer",
        remote_units_data={0: {}},
    )

    state = State(leader=True, containers=[loki_container], relations=[logging_rel])

    with patch.object(LokiOperatorCharm, "_update_cert"):
        state_out = ctx.run(ctx.on.pebble_ready(loki_container), state)

    # Check the unit relation data
    rel = state_out.get_relation(logging_rel.id)
    rel_data = rel.local_unit_data

    # Relation data must include an "endpoint" key
    assert "endpoint" in rel_data
    endpoint = json.loads(rel_data["endpoint"])

    # The endpoint must be a dict
    assert isinstance(endpoint, dict)

    # Endpoint must have a "url" key
    assert "url" in endpoint
    assert endpoint["url"].startswith("http")


def test_promtail_url(ctx, loki_container):
    """Test that promtail_binary_zip_url is set in app relation data (deprecated)."""
    logging_rel = Relation(
        "logging",
        remote_app_name="consumer",
        remote_units_data={0: {}},
    )

    state = State(leader=True, containers=[loki_container], relations=[logging_rel])

    with patch.object(LokiOperatorCharm, "_update_cert"):
        # Use relation_joined to trigger the promtail_binary_zip_url to be set
        state_out = ctx.run(ctx.on.relation_joined(logging_rel), state)

    # Check the app relation data
    rel = state_out.get_relation(logging_rel.id)
    rel_data = rel.local_app_data

    # Relation data must include a "promtail_binary_zip_url" key
    assert "promtail_binary_zip_url" in rel_data

    # The value must be a url
    promtail_binaries = json.loads(rel_data["promtail_binary_zip_url"])
    url = promtail_binaries["amd64"]["url"]
    assert url.startswith("http")


def test_promtail_url_set_on_relation_changed_if_missing(ctx, loki_container):
    """Scenario: promtail_binary_zip_url is set on relation_changed as a fallback."""
    # Start with a relation where promtail_binary_zip_url is not set (simulating missed joined)
    logging_rel = Relation(
        "logging",
        remote_app_name="consumer",
        remote_app_data={"metadata": json.dumps(METADATA)},
        remote_units_data={0: {}},
        local_app_data={},  # Empty - simulating missed relation_joined
    )

    state = State(leader=True, containers=[loki_container], relations=[logging_rel])

    with patch.object(LokiOperatorCharm, "_update_cert"):
        # Trigger relation_changed which should set promtail_binary_zip_url as fallback
        state_after_changed = ctx.run(ctx.on.relation_changed(logging_rel), state)

        # THEN promtail_binary_zip_url should be set in app data
        rel_after = state_after_changed.get_relation(logging_rel.id)
        assert "promtail_binary_zip_url" in rel_after.local_app_data
        assert rel_after.local_app_data["promtail_binary_zip_url"] != ""
        promtail_binaries = json.loads(rel_after.local_app_data["promtail_binary_zip_url"])
        url = promtail_binaries["amd64"]["url"]
        assert url.startswith("http")


# --- TestAlertRuleBlockedStatus ---


def test_alert_rule_errors_appropriately_set_state(ctx, loki_container):
    """Ensure that Loki 'keeps' BlockedStatus from alert rules until another rules event."""
    logging_rel = Relation(
        "logging",
        remote_app_name="tester",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(ALERT_RULES),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, containers=[loki_container], relations=[logging_rel])

    with patch("urllib.request.urlopen") as mock_request, patch.object(
        LokiOperatorCharm, "_update_cert"
    ):
        # Configure mock to raise HTTPError
        mock_request.side_effect = HTTPError(
            url="http://example.com",
            code=404,
            msg="fubar!",
            fp=BytesIO(initial_bytes="fubar!".encode()),
            hdrs=HTTPMessage(),
        )
        state_out = ctx.run(ctx.on.relation_changed(logging_rel), state)

    assert state_out.unit_status == BlockedStatus(
        "Failed to verify alert rules. Check juju debug-log"
    )


def test_loki_connection_errors_on_lifecycle_events_appropriately_clear(ctx, loki_container):
    """Test that connection errors are properly handled and can clear."""
    logging_rel = Relation(
        "logging",
        remote_app_name="tester",
        remote_app_data={
            "metadata": json.dumps(METADATA),
            "alert_rules": json.dumps(ALERT_RULES),
        },
        remote_units_data={0: {}},
    )

    state = State(leader=True, containers=[loki_container], relations=[logging_rel])

    with patch("urllib.request.urlopen") as mock_request, patch.object(
        LokiOperatorCharm, "_update_cert"
    ):
        # First call: error
        mock_request.side_effect = URLError(reason="fubar!")
        state_error = ctx.run(ctx.on.relation_changed(logging_rel), state)

        assert isinstance(state_error.unit_status, BlockedStatus)
        assert "Failed to verify alert rules via" in state_error.unit_status.message

        # Second call: success
        mock_request.side_effect = None
        mock_request.return_value = BytesIO(initial_bytes="success".encode())

        state_success = ctx.run(ctx.on.config_changed(), state_error)

        assert state_success.unit_status == ActiveStatus()
