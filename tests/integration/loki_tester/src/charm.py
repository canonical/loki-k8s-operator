#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Charm to functionally test the Loki Operator."""

import json
import logging
from pathlib import Path
from typing import List

from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer, \
    LokiPushApiConsumer
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, Container
from ops.pebble import Layer, ChangeError

logger = logging.getLogger(__name__)
LOGFILE = "/loki_tester_msgs.txt"


class LokiTesterCharm(CharmBase):
    """A Charm used to test the Loki charm."""

    def __init__(self, *args):
        super().__init__(*args)
        self._name = name = "loki-tester"
        self._log_py_script = (Path(__file__).parent.resolve() /
                               "log.py").absolute()
        self.log_proxy_consumer = LogProxyConsumer(
            self, log_files=[LOGFILE],
            enable_syslog=True,
            container_name=name)

        self.framework.observe(
            self.on.config_changed,
            self._on_config_changed)

    @property
    def loki_endpoints(self) -> List[dict]:
        """Fetch Loki Push API endpoints sent from LogProxyConsumer
         through relation data.

        Returns:
            A list with Loki Push API endpoints.
        """
        endpoints = []  # type: list
        for relation in self.model.relations['log-proxy']:
            endpoints = endpoints + json.loads(
                relation.data[relation.app].get("endpoints", "[]"))
        return endpoints

    def set_active_status(self):
        """Determine active status message, and set it"""
        addr = self._get_loki_url()
        msg = f'Loki ready at {addr}.' if addr else ''
        self.unit.status = ActiveStatus(msg)

    def _push_logpy(self, container: Container):
        """copy logpy script to container"""
        logpy_script = self._log_py()
        container.push("/log.py", logpy_script)
        logger.info("Pushed log.py to container")

    def _ensure_logpy_present(self, container: Container):
        try:
            self._push_logpy(container)
        except Exception as e:
            logger.debug('encountered error when pushing logpy:', e)
        assert '/log.py' in [f.path for f in container.list_files('/')], 'logpy not pushed'

    def _on_config_changed(self, event):
        """Reconfigure the Loki tester."""
        container = self.unit.get_container(self._name)
        if not container.can_connect():
            self.unit.status = BlockedStatus("Waiting for container")
            return

        logger.info(f"configured loki-tester: {self.config['log-to']}")
        self._refresh_pebble_layer()

    def one_shot_container_start(self, container: Container):
        try:
            container.start(self._name)
            logger.info('container STARTED')
        except ChangeError as exc:
            #  Start service "cmd" (cannot start service:
            #       exited quickly with code 0)
            if "exited quickly with code 0" not in exc.err:
                logger.exception("cmd FAIL")
                raise exc  # reraise, this is not good

        logger.info(f"cmd logpy [{self.config['log-to']}] OK")

    def _refresh_pebble_layer(self):
        container = self.unit.get_container(self._name)

        #  this might get called before pebble-ready, so we push logpy here
        self._ensure_logpy_present(container)

        current_services = container.get_plan().services
        new_layer = self._tester_pebble_layer()
        if current_services != new_layer.services:
            container.add_layer(self._name, new_layer, combine=True)
            logger.debug("Added tester layer to container")

            self.one_shot_container_start(container)
            logger.info("Restarted tester service")
        self.set_active_status()

    def _get_loki_url(self) -> str:
        """Fetches the loki address; only available if loki_push_api relation 
        is active.
        """
        endpoints = self.loki_endpoints
        if not endpoints:
            return ''
        return endpoints[0]['url']

    def _tester_pebble_layer(self) -> Layer:
        """Generate Loki tester pebble layer.
        """
        modes = self.config['log-to']
        loki_address = self._get_loki_url() or '<not_an_address>'
        logger.info(f'generated pebble layer with loki address: {loki_address!r}')
        cmd = f"python3 log.py {modes} {loki_address} {LOGFILE}"

        logger.info(f'pebble layer command: {cmd}')
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
            }
        }
        return Layer(layer_spec)

    def _log_py(self):
        """Fetch the log generator script."""
        with self._log_py_script.open() as script:
            return script.read()


if __name__ == "__main__":
    main(LokiTesterCharm)
