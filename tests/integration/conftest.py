# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import functools
import logging
import os
import shutil
from collections import defaultdict
from datetime import datetime

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


class Store(defaultdict):
    def __init__(self):
        super(Store, self).__init__(Store)

    def __getattr__(self, key):
        """Override __getattr__ so dot syntax works on keys."""
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        """Override __setattr__ so dot syntax works on keys."""
        self[key] = value


store = Store()


def timed_memoizer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        fname = func.__qualname__
        logger.info("Started: %s" % fname)
        start_time = datetime.now()
        if fname in store.keys():
            ret = store[fname]
        else:
            logger.info("Return for {} not cached".format(fname))
            ret = await func(*args, **kwargs)
            store[fname] = ret
        logger.info("Finished: {} in: {} seconds".format(fname, datetime.now() - start_time))
        return ret

    return wrapper


@pytest.fixture(scope="module", autouse=True)
def copy_loki_library_into_test_charms(ops_test):
    """Ensure that the tester charm uses the current Prometheus library."""
    library_path = "lib/charms/loki_k8s/v0/loki_push_api.py"
    for tester in ["loki-tester", "log-proxy-tester"]:
        install_path = "tests/integration/{}/{}".format(tester, library_path)
        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        shutil.copyfile(library_path, install_path)


@pytest.fixture(scope="module")
@timed_memoizer
async def loki_charm(ops_test: OpsTest):
    """Loki charm used for integration testing."""
    charm = await ops_test.build_charm(".")
    return charm


@pytest.fixture(scope="module")
@timed_memoizer
async def loki_tester_charm(ops_test):
    """A charm for integration test of the Loki charm."""
    charm_path = "tests/integration/loki-tester"
    clean_cmd = ["charmcraft", "clean", "-p", charm_path]
    await ops_test.run(*clean_cmd)
    bad_rule_path = "tests/integration/loki-tester/src/loki_alert_rules/free-standing/error.rule"
    try:
        os.remove(bad_rule_path)
    except FileNotFoundError:
        pass
    charm = await ops_test.build_charm(charm_path)
    return charm


@pytest.fixture(scope="module")
@timed_memoizer
async def faulty_loki_tester_charm(ops_test):
    """A faulty tester charm for integration test of the Loki charm."""
    charm_path = "tests/integration/loki-tester"

    clean_cmd = ["charmcraft", "clean", "-p", charm_path]
    await ops_test.run(*clean_cmd)

    rules_path = "tests/sample_rule_files/error/alert.rule"
    install_path = "tests/integration/loki-tester/src/loki_alert_rules/free-standing/error.rule"
    shutil.copyfile(rules_path, install_path)
    charm = await ops_test.build_charm(charm_path)
    try:
        os.remove(install_path)
    except FileNotFoundError:
        logger.warning("Failed to delete bad alert rule file")

    return charm


@pytest.fixture(scope="module")
@timed_memoizer
async def log_proxy_tester_charm(ops_test):
    """A charm for integration test of Promtail."""
    charm_path = "tests/integration/log-proxy-tester"
    clean_cmd = ["charmcraft", "clean", "-p", charm_path]
    await ops_test.run(*clean_cmd)
    charm = await ops_test.build_charm(charm_path)
    return charm
