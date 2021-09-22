#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from charms.grafana_k8s.v0.grafana_source import GrafanaSourceConsumer
from charms.loki_k8s.v0.loki import LokiProvider
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

from kubernetes_service import K8sServicePatch, PatchFailed
from loki_server import LokiServer, LokiServerError

logger = logging.getLogger(__name__)


class LokiOperatorCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    _port = 3100

    def __init__(self, *args):
        logger.debug("Initializing Charm")
        super().__init__(*args)
        self._stored.set_default(provider_ready=False, k8s_service_patched=False)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.loki_pebble_ready, self._on_loki_pebble_ready)
        self.grafana_source_consumer = GrafanaSourceConsumer(
            charm=self,
            name="grafana-source",
            refresh_event=self.on.loki_pebble_ready,
            source_type="loki",
            source_port=str(self._port),
        )
        self.loki_provider = None
        self._provide_loki()

    ##############################################
    #           CHARM HOOKS HANDLERS             #
    ##############################################
    def _on_install(self, _):
        """Handler for the install event during which we will update the K8s service."""
        self._patch_k8s_service()

    def _on_config_changed(self, _):
        if self._stored.provider_ready:
            self.unit.status = ActiveStatus()

    def _on_loki_pebble_ready(self, event):
        """Define and start a workload using the Pebble API."""
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "Loki layer",
            "description": "pebble config layer for Loki",
            "services": {
                "loki": {
                    "override": "replace",
                    "summary": "loki",
                    "command": "/usr/bin/loki -target=all -config.file=/etc/loki/local-config.yaml",
                    "startup": "enabled",
                },
            },
        }
        # Add intial Pebble config layer using the Pebble API
        container.add_layer("loki", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()

    ##############################################
    #             UTILITY METHODS                #
    ##############################################
    def _provide_loki(self):
        try:
            version = LokiServer().version
            self.loki_provider = LokiProvider(self, "logging")
            self._stored.provider_ready = True
            logger.debug("Loki Provider is available. Loki version: %s", version)
        except LokiServerError as e:
            self.unit.status = BlockedStatus(str(e))
            logger.error(str(e))

    def _patch_k8s_service(self):
        """Fix the Kubernetes service that was setup by Juju with correct port numbers."""
        if self.unit.is_leader() and not self._stored.k8s_service_patched:
            service_ports = [
                (f"{self.app.name}", self._port, self._port),
            ]
            try:
                K8sServicePatch.set_ports(self.app.name, service_ports)
            except PatchFailed as e:
                logger.error("Unable to patch the Kubernetes service: %s", str(e))
            else:
                self._stored.k8s_service_patched = True
                logger.info("Successfully patched the Kubernetes service!")


if __name__ == "__main__":
    main(LokiOperatorCharm)
