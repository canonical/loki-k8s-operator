# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import pytest_jubilant

logger = logging.getLogger(__name__)

LOKI_PUSH_API_V1_PATH = Path("lib/charms/loki_k8s/v1/loki_push_api.py")


def _pack_charm(charm_path: str) -> Path:
    """Pack a charm, working around pytest_jubilant.pack() using charmcraft's removed -p flag."""
    orig_dir = os.getcwd()
    try:
        os.chdir(charm_path)
        return pytest_jubilant.pack(".")
    finally:
        os.chdir(orig_dir)


@pytest.fixture(scope="session")
def cos_channel():
    return "2/edge"


@pytest.fixture(scope="session", autouse=True)
def copy_loki_library_into_test_charms():
    """Ensure that the tester charms use the current Loki library."""
    library_path = "lib/charms/loki_k8s/v1/loki_push_api.py"
    for tester in ["loki-tester", "log-proxy-tester"]:
        install_path = Path("tests/integration/{}/{}".format(tester, library_path))
        install_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(library_path, install_path)


@pytest.fixture(scope="session")
def loki_charm(copy_loki_library_into_test_charms):
    """Loki charm used for integration testing."""
    if charm_file := os.environ.get("CHARM_PATH"):
        return Path(charm_file)
    return pytest_jubilant.pack(".")


@pytest.fixture(scope="session")
def loki_tester_charm(copy_loki_library_into_test_charms):
    """A charm for integration test of the Loki charm."""
    charm_path = "tests/integration/loki-tester"
    subprocess.run(["charmcraft", "clean"], check=True, cwd=charm_path)
    bad_rule_path = Path("tests/integration/loki-tester/src/loki_alert_rules/free-standing/error.rule")
    bad_rule_path.unlink(missing_ok=True)
    packed = _pack_charm(charm_path)
    dest = packed.parent / "loki-tester-clean.charm"
    shutil.copy(packed, dest)
    return dest


@pytest.fixture(scope="session")
def faulty_loki_tester_charm(copy_loki_library_into_test_charms):
    """A faulty tester charm for integration test of the Loki charm."""
    charm_path = "tests/integration/loki-tester"
    subprocess.run(["charmcraft", "clean"], check=True, cwd=charm_path)
    rules_path = "tests/resources/alert.rule"
    install_path = Path("tests/integration/loki-tester/src/loki_alert_rules/free-standing/error.rule")
    shutil.copyfile(rules_path, install_path)
    try:
        packed = _pack_charm(charm_path)
        dest = packed.parent / "loki-tester-faulty.charm"
        shutil.copy(packed, dest)
        return dest
    finally:
        install_path.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def log_proxy_tester_charm(copy_loki_library_into_test_charms):
    """A charm for integration test of Promtail."""
    charm_path = "tests/integration/log-proxy-tester"
    subprocess.run(["charmcraft", "clean"], check=True, cwd=charm_path)
    return _pack_charm(charm_path)


@pytest.fixture(scope="session")
def log_forwarder_tester_charm(copy_loki_library_into_test_charms):
    """A charm for integration test of LogForwarder."""
    testingcharm_path = Path("tests") / "integration/log-forwarder-tester"

    dest_charmlib = testingcharm_path / LOKI_PUSH_API_V1_PATH
    shutil.rmtree(dest_charmlib.parent, ignore_errors=True)
    dest_charmlib.parent.mkdir(parents=True)
    os.link(LOKI_PUSH_API_V1_PATH, dest_charmlib)

    charm_path = "tests/integration/log-forwarder-tester"
    subprocess.run(["charmcraft", "clean"], check=True, cwd=charm_path)
    packed = _pack_charm(charm_path)

    shutil.rmtree(dest_charmlib.parent)
    return packed
