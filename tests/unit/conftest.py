import logging
import shlex
from unittest.mock import PropertyMock, patch

import ops
import pytest
from cosl.loki_logger import LokiHandler
from helpers import pebble_change_error
from ops.model import Container as OpsContainer
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
        execs={
            Exec(["update-ca-certificates", "--fresh"], return_code=0),
            Exec(["/usr/bin/loki", "-version"], return_code=0, stdout="loki, version 3.14159"),
        },
        layers={"loki": ops.pebble.Layer({"services": {"loki": {}}})},
        service_statuses={"loki": ops.pebble.ServiceStatus.INACTIVE},
    )


@pytest.fixture
def pebble_restart_checks_binary():
    """Make the simulated Pebble reject service starts whose executable is absent.

    The stock ops.testing Pebble mock only checks that the service exists in the
    plan; real Pebble fails the start with ``fork/exec ...: no such file or
    directory``. Use this fixture whenever a test needs that fidelity (e.g.
    regression tests for https://github.com/canonical/loki-k8s-operator/issues/659).
    """
    original_restart = OpsContainer.restart

    def restart(self, *service_names):
        plan = self.get_plan()
        for name in service_names:
            binary = shlex.split(plan.services[name].command)[0]
            try:
                self.list_files(binary)
                missing = False
            except Exception:
                missing = True
            if missing:
                raise pebble_change_error(
                    "cannot perform the following tasks:\n"
                    f'- Start service "{name}" (cannot start service: fork/exec '
                    f"{binary}: no such file or directory)"
                )
        return original_restart(self, *service_names)

    with patch.object(OpsContainer, "restart", restart):
        yield
