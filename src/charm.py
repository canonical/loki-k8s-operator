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
from ops.model import ActiveStatus

from loki_server import LokiServer

logger = logging.getLogger(__name__)


class LokiOperatorCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    loki_provider: LokiProvider = None
    port = 3100

    def __init__(self, *args):
        logger.debug("Initializing Charm")
        super().__init__(*args)
        self._stored.set_default(provider_ready=False)
        self.framework.observe(self.on.loki_pebble_ready, self._on_loki_pebble_ready)
        self.grafana_source_consumer = GrafanaSourceConsumer(
            charm=self,
            name="grafana-source",
            consumes={"Grafana": ">=2.0.0"},
            refresh_event=self.on.loki_pebble_ready,
            source_type="loki",
            source_port=str(self.port),
        )
        self._provide_loki()

    ##############################################
    #           CHARM HOOKS HANDLERS             #
    ##############################################
    def _on_loki_pebble_ready(self, event):
        """Define and start a workload using the Pebble API."""
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        target = self.config["target"]
        pebble_layer = {
            "summary": "Loki layer",
            "description": "pebble config layer for Loki",
            "services": {
                "loki": {
                    "override": "replace",
                    "summary": "loki",
                    "command": f"/usr/bin/loki -target={target} -config.file=/etc/loki/local-config.yaml",
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
        if self.provider_ready:
            self.loki_provider = LokiProvider(self, "logging", "loki", LokiServer().version)
            self.loki_provider.ready()
            logger.debug("Loki Provider is available")
            self.unit.status = ActiveStatus()

    ##############################################
    #               PROPERTIES                   #
    ##############################################
    @property
    def provider_ready(self):
        """Check status of Loki server.

        Status of the Loki services is checked by querying
        Loki for its version information. If Loki responds
        with valid information, its status is recorded.

        Returns:
            True if Loki is ready, False otherwise
        """
        provided = {"loki": LokiServer().version}

        if provided["loki"] is not None:
            logger.debug("Loki provider is available, version: %s", provided)
            self._stored.provider_ready = True

        return self._stored.provider_ready


if __name__ == "__main__":
    main(LokiOperatorCharm)
