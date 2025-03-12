# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json

from charms.grafana_k8s.v0.grafana_source import GrafanaSourceData
from scenario import Relation, State

from charm import LokiOperatorCharm


def test_sorted_source_data(context, loki_container):
    # GIVEN multiple "grafana-source" relations
    rel_1 = Relation(
        "grafana-source",
        remote_app_name="grafana_one",
        remote_app_data={
            "grafana_uid": "1",
            "datasource_uids": json.dumps({"loki/0": "first"}),
            "grafana_base_url": "http://one",
        },
    )
    rel_2 = Relation(
        "grafana-source",
        remote_app_name="grafana_two",
        remote_app_data={
            "grafana_uid": "2",
            "datasource_uids": json.dumps({"loki/0": "second"}),
            "grafana_base_url": "http://two",
        },
    )

    state_in = State(
        relations=[rel_1, rel_2],
        containers=[loki_container],
    )
    # WHEN we receive any event
    with context(context.on.update_status(), state_in) as mgr:
        charm: LokiOperatorCharm = mgr.charm
        # THEN we receive a single GrafanaSourceData instance, sorted by `grafana_uid`
        assert charm._sorted_source_data() == GrafanaSourceData({"loki/0": "first"}, "http://one")


def test_sorted_source_data_no_relations(context, loki_container):
    # GIVEN no "grafana-source" relations
    state_in = State(
        relations=[],
        containers=[loki_container],
    )
    # WHEN we receive any event
    with context(context.on.update_status(), state_in) as mgr:
        charm: LokiOperatorCharm = mgr.charm
        # THEN we receive an empty GrafanaSourceData instance
        assert charm._sorted_source_data() == GrafanaSourceData({}, "")
