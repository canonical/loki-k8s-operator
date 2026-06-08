import logging
from unittest.mock import PropertyMock, patch

import ops
import pytest
from cosl.loki_logger import LokiHandler
from ops.testing import Context
from scenario import Container, Exec

from charm import LokiOperatorCharm


def tautology(*_, **__) -> bool:
    return True


@pytest.fixture(autouse=True)
def cleanup_loki_handlers():
    """Remove any LokiHandlers from the root logger after each test.

    The charm_logging library adds LokiHandlers to the root logger during charm init,
    and these persist across test runs causing test pollution.
    """
    yield
    root_logger = logging.getLogger()
    root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, LokiHandler)]


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
