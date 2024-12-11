# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import ops
import pytest
from charms.tempo_coordinator_k8s.v0.charm_tracing import charm_tracing_disabled
from interface_tester import InterfaceTester
from ops import ActiveStatus
from scenario.state import Container, Exec, Relation, State

from charm import LokiOperatorCharm


@pytest.fixture(autouse=True, scope="module")
def patch_all():
    with ExitStack() as stack:
        stack.enter_context(patch("lightkube.core.client.GenericSyncClient"))
        stack.enter_context(
            patch.multiple(
                "charms.observability_libs.v0.kubernetes_compute_resources_patch.KubernetesComputeResourcesPatch",
                _namespace="test-namespace",
                _patch=lambda _: None,
                is_ready=MagicMock(return_value=True),
                get_status=lambda _: ActiveStatus(""),
            )
        )
        stack.enter_context(charm_tracing_disabled())

        yield


loki_container = Container(
    name="loki",
    can_connect=True,
    execs={Exec(["update-ca-certificates", "--fresh"], return_code=0)},
    layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
    service_statuses={"loki": ops.pebble.ServiceStatus.ACTIVE},
)

grafana_source_relation = Relation(
    "grafana-source",
    remote_app_data={
        "datasource_uids": json.dumps({"loki/0": "01234"}),
        "grafana_uid": "5678",
    },
)

grafana_datasource_exchange_relation = Relation(
    "send-datasource",
    remote_app_data={
        "datasources": json.dumps([{"type": "loki", "uid": "01234", "grafana_uid": "5678"}])
    },
)


@pytest.fixture
def grafana_datasource_tester(interface_tester: InterfaceTester):
    interface_tester.configure(
        charm_type=LokiOperatorCharm,
        state_template=State(
            leader=True, containers=[loki_container], relations=[grafana_source_relation]
        ),
    )
    yield interface_tester


@pytest.fixture
def grafana_datasource_exchange_tester(interface_tester: InterfaceTester):
    interface_tester.configure(
        charm_type=LokiOperatorCharm,
        state_template=State(
            leader=True,
            containers=[loki_container],
            relations=[grafana_source_relation, grafana_datasource_exchange_relation],
        ),
    )
    yield interface_tester
