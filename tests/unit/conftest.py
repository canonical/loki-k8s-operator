from unittest.mock import PropertyMock, patch

import ops
import pytest
from ops.testing import Context
from ops_tracing._mock import patch_tracing
from scenario import Container, Exec

from charm import LokiOperatorCharm


def tautology(*_, **__) -> bool:
    return True


@pytest.fixture
def loki_charm(tmp_path):
    with patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace=PropertyMock("test-namespace"),
        _patch=PropertyMock(tautology),
        is_ready=PropertyMock(tautology),
    ):
        with patch("socket.getfqdn", new=lambda *args: "fqdn"):
            with patch("lightkube.core.client.GenericSyncClient"):
                with patch_tracing():
                    yield LokiOperatorCharm


@pytest.fixture
def context(loki_charm):
    return Context(loki_charm)


@pytest.fixture(scope="function")
def loki_container():
    return Container(
        "loki",
        can_connect=True,
        execs={Exec(["update-ca-certificates", "--fresh"], return_code=0)},
        layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
        service_statuses={"loki": ops.pebble.ServiceStatus.INACTIVE},
    )
