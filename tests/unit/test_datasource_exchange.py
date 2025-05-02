# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import pytest
from cosl.interfaces.datasource_exchange import (
    DatasourceExchange,
    DSExchangeAppData,
    GrafanaDatasource,
)
from scenario import Relation, State

from src.charm import LokiOperatorCharm

ds_tempo = [
    {"type": "tempo", "uid": "3", "grafana_uid": "4"},
]

ds_mimir = [
    {"type": "prometheus", "uid": "8", "grafana_uid": "9"},
]

mimir_dsx = Relation(
    "send-datasource",
    remote_app_data=dict(DSExchangeAppData(datasources=json.dumps(ds_mimir)).dump()),  # type: ignore
)
tempo_dsx = Relation(
    "send-datasource",
    remote_app_data=dict(DSExchangeAppData(datasources=json.dumps(ds_tempo)).dump()),  # type: ignore
)

ds = Relation(
    "grafana-source",
    remote_app_data={
        "grafana_uid": "9",
        "datasource_uids": json.dumps({"loki/0": "1234"}),
    },
)


@pytest.mark.skip(
    "Skipping this until we decide on how to fix it, reconciler pattern vs observing the events"
)
@pytest.mark.parametrize("event_type", ("changed", "created", "joined"))
@pytest.mark.parametrize("relation_to_observe", (ds, mimir_dsx, tempo_dsx))
def test_datasource_send(context, loki_container, relation_to_observe, event_type):
    state_in = State(
        relations=[
            ds,
            mimir_dsx,
            tempo_dsx,
        ],
        containers=[loki_container],
        leader=True,
    )

    # WHEN we receive a datasource-related event
    with context(
        getattr(context.on, f"relation_{event_type}")(relation_to_observe), state_in
    ) as mgr:
        charm: LokiOperatorCharm = mgr.charm
        # THEN we can find all received datasource uids
        dsx: DatasourceExchange = charm.datasource_exchange  # type: ignore
        received = dsx.received_datasources
        assert received == (
            GrafanaDatasource(type="tempo", uid="3", grafana_uid="4"),
            GrafanaDatasource(type="prometheus", uid="8", grafana_uid="9"),
        )
        state_out = mgr.run()

    # AND THEN we publish our own datasource information to mimir and tempo
    published_dsx_mimir = state_out.get_relation(mimir_dsx.id).local_app_data
    published_dsx_tempo = state_out.get_relation(tempo_dsx.id).local_app_data
    assert published_dsx_tempo == published_dsx_mimir
    assert json.loads(published_dsx_tempo["datasources"])[0] == {
        "type": "loki",
        "uid": "1234",
        "grafana_uid": "9",
    }
