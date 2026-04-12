# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)

LOKI_PUSH_API_V1_PATH = Path("lib/charms/loki_k8s/v1/loki_push_api.py")


def _pack_charm(charm_path: str) -> Path:
    """Pack a charm.

    Copied from pytest-jubilant 1.x, which no longer provides pack() in 2.0.
    """
    orig_dir = os.getcwd()
    try:
        os.chdir(charm_path)
        cmd = "charmcraft pack"
        proc = subprocess.run(
            shlex.split(cmd),
            check=True,
            capture_output=True,
            text=True,
        )
        # Don't ask me why this goes to stderr.
        output = proc.stderr
        packed_charms = []
        for line in output.strip().splitlines():
            if line.startswith("Packed"):
                packed_charms.append(line.split()[1])
        if not packed_charms:
            raise ValueError(
                f"unable to get packed charm(s) ({cmd!r} completed with "
                f"{proc.returncode=}, {proc.stdout=}, {proc.stderr=})"
            )
        if len(packed_charms) > 1:
            raise ValueError(
                "This charm supports multiple platforms. "
                "Pass a `platform` argument to control which charm you're getting instead."
            )
        return Path(packed_charms[0]).resolve()
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
    return _pack_charm(".")


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
