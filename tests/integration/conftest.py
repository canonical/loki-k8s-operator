# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import os
import shutil
from pathlib import Path
from typing import Dict

import jubilant
import pytest
import sh
import yaml

logger = logging.getLogger(__name__)

LOKI_PUSH_API_V1_PATH = Path("lib/charms/loki_k8s/v1/loki_push_api.py")


@pytest.fixture(scope="session")
def cos_channel():
    return "2/edge"


@pytest.fixture(scope="module")
def juju():
    keep_models: bool = os.environ.get("KEEP_MODELS") is not None
    with jubilant.temp_model(keep=keep_models) as juju:
        juju.wait_timeout = 30 * 60
        yield juju


@pytest.fixture(scope="module", autouse=True)
def copy_loki_library_into_test_charms():
    """Ensure that the tester charm uses the current Loki library."""
    library_path = "lib/charms/loki_k8s/v1/loki_push_api.py"
    for tester in ["loki-tester", "log-proxy-tester"]:
        install_path = f"tests/integration/{tester}/{library_path}"
        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        shutil.copyfile(library_path, install_path)


@pytest.fixture(scope="module")
def loki_charm():
    """Loki charm used for integration testing."""
    if charm_file := os.environ.get("CHARM_PATH"):
        return Path(charm_file).absolute()

    sh.charmcraft.pack()  # type: ignore
    charms = sorted(Path(".").glob("*.charm"))
    assert charms, "No .charm file found after 'charmcraft pack'"
    return charms[-1].resolve()


@pytest.fixture(scope="module")
def loki_resources(metadata_file: str = "charmcraft.yaml") -> Dict[str, str]:
    """Get Loki charm resources from charmcraft.yaml."""
    with open(metadata_file, "r") as file:
        metadata = yaml.safe_load(file)
    resources = {}
    for res, data in metadata["resources"].items():
        resources[res] = data["upstream-source"]
    return resources


@pytest.fixture(scope="module")
def loki_tester_charm():
    """A charm for integration test of the Loki charm."""
    charm_path = Path("tests/integration/loki-tester")
    bad_rule_path = charm_path / "src/loki_alert_rules/free-standing/error.rule"
    try:
        os.remove(bad_rule_path)
    except FileNotFoundError:
        pass
    sh.charmcraft.pack(_cwd=charm_path)  # type: ignore
    charms = sorted(charm_path.glob("*.charm"))
    assert charms, f"No .charm file found in {charm_path}"
    return charms[-1].resolve()


@pytest.fixture(scope="module")
def faulty_loki_tester_charm():
    """A faulty tester charm for integration test of the Loki charm."""
    charm_path = Path("tests/integration/loki-tester")
    rules_path = Path("tests/resources/alert.rule")
    install_path = charm_path / "src/loki_alert_rules/free-standing/error.rule"
    shutil.copyfile(rules_path, install_path)
    sh.charmcraft.pack(_cwd=charm_path)  # type: ignore
    charms = sorted(charm_path.glob("*.charm"))
    assert charms, f"No .charm file found in {charm_path}"
    try:
        os.remove(install_path)
    except FileNotFoundError:
        logger.warning("Failed to delete bad alert rule file")
    return charms[-1].resolve()


@pytest.fixture(scope="module")
def log_proxy_tester_charm():
    """A charm for integration test of Promtail (deprecated).

    Deprecated: This fixture builds the log-proxy-tester charm, which uses LogProxyConsumer
    and Promtail. Promtail is deprecated by Grafana. New integrations should use
    LokiPushApiConsumer with OpenTelemetry Collector instead.
    """
    charm_path = Path("tests/integration/log-proxy-tester")
    sh.charmcraft.pack(_cwd=charm_path)  # type: ignore
    charms = sorted(charm_path.glob("*.charm"))
    assert charms, f"No .charm file found in {charm_path}"
    return charms[-1].resolve()


@pytest.fixture(scope="module")
def log_forwarder_tester_charm():
    """A charm for integration test of LogForwarder."""
    testingcharm_path = Path("tests/integration/log-forwarder-tester")
    dest_charmlib = testingcharm_path / LOKI_PUSH_API_V1_PATH
    shutil.rmtree(dest_charmlib.parent, ignore_errors=True)
    dest_charmlib.parent.mkdir(parents=True)
    dest_charmlib.hardlink_to(LOKI_PUSH_API_V1_PATH)

    sh.charmcraft.pack(_cwd=testingcharm_path)  # type: ignore
    charms = sorted(testingcharm_path.glob("*.charm"))
    assert charms, f"No .charm file found in {testingcharm_path}"
    shutil.rmtree(dest_charmlib.parent)
    return charms[-1].resolve()


@pytest.fixture(scope="module")
def log_proxy_tester_resources() -> Dict[str, str]:
    """Get log-proxy-tester charm resources."""
    metadata_file = "tests/integration/log-proxy-tester/charmcraft.yaml"
    with open(metadata_file, "r") as file:
        metadata = yaml.safe_load(file)
    resources = {}
    for res, data in metadata["resources"].items():
        resources[res] = data["upstream-source"]
    return resources


@pytest.fixture(scope="module")
def log_forwarder_tester_resources() -> Dict[str, str]:
    """Get log-forwarder-tester charm resources."""
    metadata_file = "tests/integration/log-forwarder-tester/charmcraft.yaml"
    with open(metadata_file, "r") as file:
        metadata = yaml.safe_load(file)
    resources = {}
    for res, data in metadata["resources"].items():
        resources[res] = data["upstream-source"]
    return resources
