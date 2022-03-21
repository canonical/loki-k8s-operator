#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import sys
import typing
from pathlib import Path
from subprocess import PIPE, Popen
from unittest.mock import patch

import pytest
from requests import get

SYSLOG_LOG_MSG = "LOG SYSLOG"
LOKI_LOG_MSG = "LOG LOKI"
FILE_LOG_MSG = "LOG FILE"


def get_logpy_path() -> Path:
    """Return the Path to log.py file in loki-tester."""
    pth = Path(__file__).parent.parent.resolve() / "integration" / "loki_tester" / "src" / "log.py"
    print(pth)
    assert pth.exists(), pth
    return pth.absolute()


XFAIL_SYSLOG_TEST = True
LOG_DEVICE_ADDRESS: typing.Optional[str]
if sys.platform == "darwin":
    LOG_DEVICE_ADDRESS = "/var/run/syslog"
elif "linux" in sys.platform:
    LOG_DEVICE_ADDRESS = "/dev/log"
else:
    # TODO: support windows as well?
    LOG_DEVICE_ADDRESS = None
    XFAIL_LOG_TEST = True


# to run this test against a locally available LOKI node:
# LOKI_ADDRESS="10.1.94.35:3100" pytest ./tests/integration/test_loki_tester.py::test_log_script
@pytest.mark.parametrize("modes", ("syslog", "loki", "file", "NOOP", "ALL"))
@patch("tests.integration.loki_tester.src.log.SYSLOG_ADDRESS", LOG_DEVICE_ADDRESS)
def test_log_script(modes, tmp_path):
    if modes == "ALL":
        modes = "syslog,loki,file"

    loki_address: str = "<not_an_address>"
    if "loki" in modes:
        env_loki_address = os.environ.get("LOKI_ADDRESS")
        if not env_loki_address:
            # todo find a way to unittest this with a running loki instance
            pytest.xfail(
                "set envvar LOKI_ADDRESS to a reachable Loki "
                "node address for the `loki`-mode test to work"
            )
        else:
            loki_address = env_loki_address

    logfile = tmp_path / "logpy.log"
    args = ["python3", get_logpy_path(), modes, loki_address, str(logfile)]
    if loki_address:
        args.append(loki_address)

    proc = Popen(args, stdout=PIPE, stderr=PIPE)
    proc.wait()

    if "syslog" in modes:
        if XFAIL_SYSLOG_TEST:
            pytest.xfail("this test is not supported on windows")
        with open("/var/log/syslog", "rb") as f:
            logs = f.read().decode(errors="replace")
            assert SYSLOG_LOG_MSG in logs

    if "loki" in modes:
        resp = get(f"http://{loki_address}/loki/api/v1/label/test/values")
        result = resp.json()
        assert result["status"] == "success"
        assert LOKI_LOG_MSG in result["data"]

    if "file" in modes:
        assert logfile.exists(), (proc.stdout.read(), proc.stderr.read())
        with open(logfile, "r") as f:
            assert FILE_LOG_MSG in f.read()
