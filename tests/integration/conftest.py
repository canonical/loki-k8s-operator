# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import shutil

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def copy_loki_library_into_tester_charm(ops_test):
    """Ensure that the tester charm uses the current Prometheus library."""
    library_path = "lib/charms/loki_k8s/v0/loki_push_api.py"
    install_path = "tests/integration/loki-tester/" + library_path
    shutil.copyfile(library_path, install_path)


@pytest.fixture(scope="module", autouse=True)
def copy_sample_alerts_into_tester_charm(ops_test):
    """Ensure that the tester charm uses the current Prometheus library."""
    rules_path = "tests/sample_rule_files/free-standing/alerting"
    install_path = "tests/integration/loki-tester/src/loki_alert_rules/free-standing"
    shutil.copytree(rules_path, install_path, dirs_exist_ok=True)


@pytest.fixture(scope="module")
async def loki_charm(ops_test: OpsTest):
    """Loki charm used for integration testing."""
    charm = await ops_test.build_charm(".")
    return charm


@pytest.fixture(scope="module")
async def loki_tester_charm(ops_test):
    """A charm for integration test of the Loki charm."""
    charm_path = "tests/integration/loki-tester"
    charm = await ops_test.build_charm(charm_path)
    return charm
