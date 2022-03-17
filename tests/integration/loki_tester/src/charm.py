#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Charm to functionally test the Loki Operator."""
import contextlib
import json
import logging
from pathlib import Path
from typing import List

from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer, \
    LokiPushApiConsumer
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, Container, WaitingStatus
from ops.pebble import ChangeError, Layer

logger = logging.getLogger(__name__)
LOGFILE = "/loki_tester_msgs.txt"


@contextlib.contextmanager
def _catch_quick_exit_errors():
    try:
        yield
    except ChangeError as exc:
        #  Start service "cmd" (cannot start service:
        #       exited quickly with code 0)
        if "exited quickly with code 0" not in exc.err:
            logger.exception("cmd FAIL")
            raise exc  # reraise, this is not good


class LokiTesterCharm(CharmBase):
    """A Charm used to test the Loki charm."""

    def __init__(self, *args):
        super().__init__(*args)
        self._name = name = "loki-tester"
        self.container = self.unit.get_container(self._name)

        this_dir = Path(__file__).parent.resolve()
        self._log_py_script = (this_dir / "log.py").absolute()
        self.log_proxy_consumer = LogProxyConsumer(
            self,
            log_files=[LOGFILE],
            enable_syslog=True,
            container_name=name
        )

        self.framework.observe(
            self.on.loki_tester_pebble_ready,
            self._on_pebble_ready)
        self.framework.observe(
            self.on.config_changed,
            self._on_config_changed)
        self.framework.observe(
            self.log_proxy_consumer.on.log_proxy_endpoint_joined,
            self._on_log_proxy_joined)

    @property
    def _loki_endpoints(self) -> List[dict]:
        """Fetch Loki Push API endpoints.

         As sent from LogProxyConsumer through relation data.

        Returns:
            A list with Loki Push API endpoints.
        """
        endpoints = []  # type: list
        for relation in self.model.relations["log-proxy"]:
            endpoints = endpoints + json.loads(relation.data[relation.app].get("endpoints", "[]"))
        return endpoints

    def _on_log_proxy_joined(self, event):
        self._refresh_pebble_layer()
        self._set_active_status()

    def _set_active_status(self):
        """Determine active status message, and set it."""
        addr = self._get_loki_url()
        if not addr:
            self.unit.status = WaitingStatus('Waiting for Loki.')
            return
        msg = f"Loki ready at {addr}." if addr else ""
        self.unit.status = ActiveStatus(msg)

    def _on_pebble_ready(self, event):
        self._ensure_logpy_present()
        self._set_active_status()

    def _ensure_logpy_present(self):
        with self._log_py_script.open() as script:
            logpy_script = script.read()
            self.container.push("/log.py", logpy_script)
            logger.info("Pushed log.py to container")

        filepaths = [f.path for f in self.container.list_files("/")]
        assert "/log.py" in filepaths, "logpy not pushed"

    def _on_config_changed(self, event):
        """Reconfigure the Loki tester."""
        if not self.container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container")
            event.defer()
            return

        if not self._get_loki_url():
            self.unit.status = WaitingStatus(
                'Waiting for loki (config-changed).'
            )
            event.defer()
            return

        logger.info(f"configured loki-tester: {self.config['log-to']}")
        self._refresh_pebble_layer()
        self._set_active_status()

    def _one_shot_container_start(self):
        with _catch_quick_exit_errors():
            self.container.start(self._name)
            logger.info("container STARTED")
        logger.info(f"cmd logpy [{self.config['log-to']}] OK")

    def _refresh_pebble_layer(self):
        #  this might get called before pebble-ready, so we check this here too
        self._ensure_logpy_present()

        current_services = self.container.get_plan().services
        new_layer = self._tester_pebble_layer()
        if current_services != new_layer.services:
            self.container.add_layer(self._name, new_layer, combine=True)
            logger.debug("Added tester layer to container")

            self._one_shot_container_start()
            logger.info("Restarted tester service")

    def _get_loki_url(self) -> str:
        """Fetches the loki address.

        Only available if some loki relation is active.
        """
        endpoints = self._loki_endpoints
        # e.g. [{'url': 'http://url:3100/loki/api/v1/push'}]
        if not endpoints:
            return ""
        return endpoints[0]["url"]

    def _tester_pebble_layer(self) -> Layer:
        """Generate Loki tester pebble layer."""
        modes = self.config["log-to"]
        loki_address = self._get_loki_url() or "<not_an_address>"
        logger.info(
            f"generated pebble layer with loki address: {loki_address!r}")
        cmd = f"python3 log.py {modes} {loki_address} {LOGFILE}"

        logger.info(f"pebble layer command: {cmd}")
        layer_spec = {
            "summary": "loki tester",
            "description": "a test data generator for Loki",
            "services": {
                self._name: {
                    "override": "replace",
                    "summary": "logger service",
                    "command": cmd,
                    "startup": "enabled",
                }
            },
        }
        return Layer(layer_spec)


if __name__ == "__main__":
    main(LokiTesterCharm)
