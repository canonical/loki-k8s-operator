from unittest.mock import PropertyMock, patch

import pytest
import scenario
from charm import LokiOperatorCharm


def tautology(*_, **__) -> bool:
    return True


@pytest.fixture
def loki_charm():
    with (
        patch.multiple(
            "charm.KubernetesComputeResourcesPatch",
            _namespace=PropertyMock("test-namespace"),
            _patch=PropertyMock(tautology),
            is_ready=PropertyMock(tautology),
        ),
        patch("socket.getfqdn", new=lambda *args: "fqdn"),
        patch("lightkube.core.client.GenericSyncClient"),
    ):
        yield LokiOperatorCharm


@pytest.fixture
def context(loki_charm):
    return scenario.Context(loki_charm)
