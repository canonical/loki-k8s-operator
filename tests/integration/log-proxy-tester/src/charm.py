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

        self._enable_syslog = self.model.config.get("syslog")
        self._enable_file_forwarding = self.model.config.get("file_forwarding")
        self._log_files = ["/bin/driver.log"]

        self._log_proxy = LogProxyConsumer(
            charm=self,
            container_name="workload",
            enable_syslog=self._enable_syslog,
            log_files=self._log_files if self._enable_file_forwarding else [],
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

    def _build_command(
        self,
        format: str = "apache_common",
        output_type: "str" = "log",
        *,
        output_filename: str = "/bin/driver.log",
    ):
        cmd = (
            f"/bin/flog --format {format} --loop --type {output_type} --overwrite "
            f"--rate {self.model.config['rate']} "
        )

        if output_type == "log":
            cmd += f"--output {output_filename} "

        if rotate := self.model.config.get("rotate"):
            cmd += f"--rotate {rotate} "

        return cmd

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

        if self._enable_syslog:
            command = self._build_command("rfc5424", "stdout")
            # TODO: UDP support in Promtail merged on 04052022. Get a new Promtail and use
            # UCP transport when it releases
            services.update(
                # Loop this command forever since it will fail if no promtail is listening, but
                # we still want the pebble services to start
                self._build_service_template(
                    "syslog",
                    f"/usr/bin/bash -c 'while true; do {command} | logger -n 127.0.0.1 -P 1514 -T --socket-errors=off || true; done'",
                )
            )
        if self._enable_file_forwarding:
            services.update(self._build_service_template("file-logger", self._build_command()))

        return services

    def _flog_layer(self) -> Layer:

        return Layer(
            {
                "summary": "flog layer",
                "description": "pebble config layer for flog",
                "services": self._build_services(),
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
