#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Log proxy test driver."""

import logging

from charms.loki_k8s.v1.loki_push_api import LogForwarder
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, Layer

logger = logging.getLogger(__name__)

LOGGING_RELATION_NAME = "log-forwarder"


class LogForwarderTesterCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        self._logging = LogForwarder(charm=self, relation_name=LOGGING_RELATION_NAME)

        self.framework.observe(self.on.workload_a_pebble_ready, self._on_workload_pebble_ready)
        self.framework.observe(self.on.workload_b_pebble_ready, self._on_workload_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_workload_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        container = event.workload
        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        try:
            self._update_layer(container)
        except (ModelError, TypeError, ChangeError) as e:
            self.unit.status = BlockedStatus("Layer update failed: {}".format(str(e)))
        else:
            self.unit.status = ActiveStatus()

    @property
    def _command(self):
        return "/bin/flog --format apache_common --loop --type stdout "

    def _build_service_template(self, name: str, command: str) -> dict:
        return {
            f"flog-{name}": {
                "override": "replace",
                "summary": "logger",
                "command": command,
                "startup": "enabled",
            }
        }

    def _build_services(self) -> dict:
        services = {}

        services.update(self._build_service_template("file-logger", self._command))

        return services

    def _flog_layer(self) -> Layer:
        return Layer(
            {
                "summary": "flog layer",
                "description": "pebble config layer for flog",
                "services": self._build_services(),
            }
        )

    def _update_layer(self, container):
        plan = container.get_plan()
        overlay = self._flog_layer()

        if overlay.services != plan.services:
            container.add_layer("flog layer", overlay, combine=True)
            container.replan()

    def _on_config_changed(self, event):
        container_a = self.unit.get_container("workload-a")
        if container_a.can_connect():
            self._update_layer(container_a)

        container_b = self.unit.get_container("workload-b")
        if container_b.can_connect():
            self._update_layer(container_b)


if __name__ == "__main__":
    main(LogForwarderTesterCharm)
