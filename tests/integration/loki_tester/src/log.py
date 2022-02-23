#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import sys
from time import time, sleep
from typing import Optional
from urllib import request


DEBUG = False
SYSLOG_LOG_MSG = "LOG SYSLOG"
LOKI_LOG_MSG = "LOG LOKI"
FILE_LOG_MSG = "LOG FILE"
WAIT = 0.5


def _log_to_syslog():
    # will print to syslog something like:
    # Feb 18 13:04:23 darkstar python3: 3
    try:
        import syslog
        syslog.syslog(SYSLOG_LOG_MSG)
    except ImportError:
        raise RuntimeError("This is only going to work on UNIX.")


def _log_to_loki(loki_address):
    # `loki_address` is the address of the push endpoint e.g.
    # 'http://loki-k8s-0.loki-k8s-endpoints.cos.svc.cluster.local:3100/loki/api/v1/push'
    loki_base_url = loki_address[:-17]

    try:
        with request.urlopen(f"{loki_base_url}/ready") as resp:
            resp_text = resp.read()
    except Exception as e:
        raise RuntimeError(
            f'Could not contact loki api at {loki_base_url}; gotten {e}')

    if not resp_text.decode('ascii').strip() == 'ready':
        print('loki not ready yet... give it time.')
        sys.exit()

    data = {
        "streams": [
            {
                "stream": {'test': 'test'},
                "values": [[str(int(time())) + '0'*9, LOKI_LOG_MSG]]
            }
        ]
    }

    enc = json.dumps(data).encode('ascii')
    req = request.Request(loki_address)
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('Content-Length', len(enc))

    try:
        with request.urlopen(req, enc) as resp:
            resp

    except Exception as e:
        raise RuntimeError(
            f'Could not contact loki api at {loki_address}; gotten {e}')

    if resp.getcode() != 204:
        raise RuntimeError(
            f"contacted loki, but request didn't go well: "
            f"gotten {resp.status_code}: {resp.reason}"
        )


def _log_to_file(fname: str):
    with open(fname, 'w+') as f:
        f.write(FILE_LOG_MSG)


def _log(mode, loki_address: str, fname: str):
    if mode == 'syslog':
        _log_to_syslog()
    elif mode == 'loki':
        if not loki_address:
            raise RuntimeError(
                'loki_address needs to be provided when in `loki` mode'
            )
        _log_to_loki(loki_address)
    elif mode == 'file':
        if not fname:
            raise RuntimeError(
                'fname needs to be provided when in `file` mode'
            )
        _log_to_file(fname)
    else:
        raise ValueError(f"unknown logging mode: {str!r}")


def main(modes: str,
         loki_address: Optional[str] = None,
         fname: Optional[str] = None):
    if modes == 'ALL':
        modes = ['syslog', 'loki', 'file']
    else:
        modes = modes.split(',')

    # we do it a few times so we have the time to inspect the running process
    # when debugging
    for _ in range(200):
        if not modes:
            break
        for mode in modes:
            try:
                _log(mode, loki_address, fname)
            except Exception as e:
                if DEBUG:
                    raise e
                print(f'failed to _log({mode!r}, {loki_address!r}, {fname!r}); '
                      'got {e}')
                modes.remove(mode)
        sleep(WAIT)


if __name__ == "__main__":
    main(*sys.argv[1:4])
