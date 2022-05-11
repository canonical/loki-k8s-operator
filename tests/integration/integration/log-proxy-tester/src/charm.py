#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Log proxy test driver."""

import logging

from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, Layer

logger = logging.getLogger(__name__)


class LogProxyTesterCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        self._log_proxy = LogProxyConsumer(
            charm=self, log_files=["/bin/driver.log"], container_name="workload"
        )
        self.framework.observe(
            self._log_proxy.on.promtail_digest_error,
            self._promtail_error,
        )

        self.framework.observe(self.on.workload_pebble_ready, self._on_workload_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _promtail_error(self, event):
        logger.error(event.message)
        self.unit.status = BlockedStatus(event.message)

    def _on_workload_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        container = self.unit.get_container("workload")
        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        try:
            self._update_layer()
        except (ModelError, TypeError, ChangeError) as e:
            self.unit.status = BlockedStatus("Layer update failed: {}".format(str(e)))
        else:
            self.unit.status = ActiveStatus()

    def _flog_layer(self) -> Layer:
        def command():
            cmd = (
                "/bin/flog --format rfc5424 --loop --type log --output /bin/driver.log --overwrite "
                f"--rate {self.model.config['rate']} "
            )

            if rotate := self.model.config.get("rotate"):
                cmd += f"--rotate {rotate} "

            return cmd

        return Layer(
            {
                "summary": "flog layer",
                "description": "pebble config layer for flog",
                "services": {
                    "flog": {
                        "override": "replace",
                        "summary": "flog service",
                        "command": command(),
                        "startup": "enabled",
                    }
                },
            }
        )

    def _update_layer(self):
        container = self.unit.get_container("workload")  # container name from metadata.yaml
        plan = container.get_plan()
        overlay = self._flog_layer()

        if overlay.services != plan.services:
            container.add_layer("flog layer", overlay, combine=True)
            container.replan()

    def _on_config_changed(self, event):
        container = self.unit.get_container("workload")
        if container.can_connect():
            self._update_layer()


if __name__ == "__main__":
    main(LogProxyTesterCharm)
