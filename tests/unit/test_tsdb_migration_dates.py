# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Scenario tests for the TSDB schema migration date logic."""

import datetime
from unittest.mock import patch

import yaml
from scenario import State

from charm import LokiOperatorCharm
from config_builder import LOKI_CONFIG


def _mock_backup(v13_date="", v12_date=""):
    """Return a callable for patching _get_schema_config_version_migration_date_from_backup.

    The returned function mirrors the real method signature (self, sc_version)
    and looks up the requested schema version in the provided mapping.
    """
    return lambda self, sc_version: {"v13": v13_date, "v12": v12_date}.get(sc_version, "")


def test_fresh_install_no_backup_uses_today(context, loki_container):
    """GIVEN no log chunks and no backup config dates.

    WHEN _tsdb_versions_migration_dates is accessed
    THEN the v13 date should be today.
    """
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(LokiOperatorCharm, "_chunks_non_empty", return_value=False), patch.object(
        LokiOperatorCharm,
        "_get_schema_config_version_migration_date_from_backup",
        return_value="",
    ):
        with context(context.on.config_changed(), state_in) as mgr:
            dates = mgr.charm._tsdb_versions_migration_dates

    v13_entries = [d for d in dates if d["version"] == "v13"]
    assert len(v13_entries) == 1
    expected = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    assert v13_entries[0]["date"] == expected


def test_fresh_install_with_backup_preserves_date(context, loki_container):
    """GIVEN no log chunks and backup config already has a v13 date.

    WHEN _tsdb_versions_migration_dates is accessed after a pod churn
    THEN the backup date takes precedence over today.
    """
    original_date = "2026-01-15"
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(LokiOperatorCharm, "_chunks_non_empty", return_value=False), patch.object(
        LokiOperatorCharm,
        "_get_schema_config_version_migration_date_from_backup",
        new=_mock_backup(v13_date=original_date),
    ):
        with context(context.on.config_changed(), state_in) as mgr:
            dates = mgr.charm._tsdb_versions_migration_dates

    v13_entries = [d for d in dates if d["version"] == "v13"]
    assert len(v13_entries) == 1
    assert v13_entries[0]["date"] == original_date


def test_upgrade_with_backup_preserves_date(context, loki_container):
    """GIVEN log chunks exist and backup config already has a v13 date.

    WHEN _tsdb_versions_migration_dates is accessed
    THEN the persisted backup date must be used.
    """
    original_date = "2026-01-15"
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(LokiOperatorCharm, "_chunks_non_empty", return_value=True), patch.object(
        LokiOperatorCharm,
        "_get_schema_config_version_migration_date_from_backup",
        new=_mock_backup(v13_date=original_date),
    ):
        with context(context.on.config_changed(), state_in) as mgr:
            dates = mgr.charm._tsdb_versions_migration_dates

    v13_entries = [d for d in dates if d["version"] == "v13"]
    assert len(v13_entries) == 1
    assert v13_entries[0]["date"] == original_date


def test_chunks_exist_no_backup_uses_tomorrow(context, loki_container):
    """GIVEN log chunks exist and no v12/v13 dates are in backup.

    WHEN _tsdb_versions_migration_dates is accessed
    THEN the v13 date should be tomorrow to preserve today's v11/v12 logs.
    """
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(LokiOperatorCharm, "_chunks_non_empty", return_value=True), patch.object(
        LokiOperatorCharm,
        "_get_schema_config_version_migration_date_from_backup",
        return_value="",
    ):
        with context(context.on.config_changed(), state_in) as mgr:
            dates = mgr.charm._tsdb_versions_migration_dates

    v13_entries = [d for d in dates if d["version"] == "v13"]
    assert len(v13_entries) == 1
    expected = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert v13_entries[0]["date"] == expected


def test_v13_date_stable_across_config_changed_events(context, loki_container):
    """GIVEN a fully configured Loki with a v13 date already pushed.

    WHEN config-changed fires again (e.g. pod churn on a later day)
    THEN the v13 date in the config pushed to the container must remain unchanged.
    """
    state_in = State(containers=[loki_container], leader=True)

    # Run 1: charm computes the v13 date (no backup present) and writes it to
    # both LOKI_CONFIG and LOKI_CONFIG_BACKUP.
    with patch.object(LokiOperatorCharm, "_update_cert"):
        with context(context.on.config_changed(), state_in) as mgr_1:
            state_out_1 = mgr_1.run()

    fs = state_out_1.get_container("loki").get_filesystem(context)
    config = yaml.safe_load((fs / LOKI_CONFIG.lstrip("/")).read_text())
    original_v13_date = next(
        (sc["from"] for sc in config["schema_config"]["configs"] if sc.get("schema") == "v13"),
        None,
    )
    assert original_v13_date is not None, "v13 schema must be present after the first run"

    # Run 2: the backup file from run 1 is now part of the input state.
    # The charm must read from the backup and reuse the same v13 date.
    with patch.object(LokiOperatorCharm, "_update_cert"):
        with context(context.on.config_changed(), state_out_1) as mgr_2:
            state_out_2 = mgr_2.run()

    fs2 = state_out_2.get_container("loki").get_filesystem(context)
    config2 = yaml.safe_load((fs2 / LOKI_CONFIG.lstrip("/")).read_text())
    v13_date_after = next(
        (sc["from"] for sc in config2["schema_config"]["configs"] if sc.get("schema") == "v13"),
        None,
    )
    assert original_v13_date == v13_date_after


def test_v12_in_backup_signals_upgrade_even_without_peer_data(context, loki_container):
    """GIVEN log chunks exist and backup has v12 but no v13 entry.

    WHEN _tsdb_versions_migration_dates is accessed
    THEN v13 must be 1 day after the v12 migration date.
    """
    v12_date = "2025-06-01"
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(LokiOperatorCharm, "_chunks_non_empty", return_value=True), patch.object(
        LokiOperatorCharm,
        "_get_schema_config_version_migration_date_from_backup",
        new=_mock_backup(v12_date=v12_date),
    ):
        with context(context.on.config_changed(), state_in) as mgr:
            dates = mgr.charm._tsdb_versions_migration_dates

    v13_entries = [d for d in dates if d["version"] == "v13"]
    assert len(v13_entries) == 1
    expected = (
        datetime.datetime.strptime(v12_date, "%Y-%m-%d") + datetime.timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert v13_entries[0]["date"] == expected


def test_allow_structured_metadata_false_when_v13_is_future(context, loki_container):
    """GIVEN a config where v13 starts tomorrow.

    WHEN config-changed fires
    THEN allow_structured_metadata must be false to avoid Loki rejecting the config.
    """
    tomorrow = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    ).strftime("%Y-%m-%d")
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(
        LokiOperatorCharm,
        "_tsdb_versions_migration_dates",
        new_callable=lambda: property(lambda self: [{"version": "v13", "date": tomorrow}]),
    ):
        with patch.object(LokiOperatorCharm, "_update_cert"):
            with context(context.on.config_changed(), state_in) as mgr:
                state_out = mgr.run()

    fs = state_out.get_container("loki").get_filesystem(context)
    config = yaml.safe_load((fs / LOKI_CONFIG.lstrip("/")).read_text())
    assert config["limits_config"]["allow_structured_metadata"] is False


def test_allow_structured_metadata_true_when_v13_is_today(context, loki_container):
    """GIVEN a config where v13 starts today.

    WHEN config-changed fires
    THEN allow_structured_metadata must be true.
    """
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    state_in = State(containers=[loki_container], leader=True)

    with patch.object(
        LokiOperatorCharm,
        "_tsdb_versions_migration_dates",
        new_callable=lambda: property(lambda self: [{"version": "v13", "date": today}]),
    ):
        with patch.object(LokiOperatorCharm, "_update_cert"):
            with context(context.on.config_changed(), state_in) as mgr:
                state_out = mgr.run()

    fs = state_out.get_container("loki").get_filesystem(context)
    config = yaml.safe_load((fs / LOKI_CONFIG.lstrip("/")).read_text())
    assert config["limits_config"]["allow_structured_metadata"] is True
