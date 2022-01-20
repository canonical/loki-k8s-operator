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
import os
import textwrap

import yaml
from charms.alertmanager_k8s.v0.alertmanager_dispatch import AlertmanagerConsumer
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceConsumer
from charms.loki_k8s.v0.loki_push_api import LokiPushApiProvider
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import PathError, ProtocolError

from kubernetes_service import K8sServicePatch, PatchFailed
from loki_server import LokiServer, LokiServerError, LokiServerNotReadyError

# Paths in workload container
LOKI_CONFIG = "/etc/loki/local-config.yaml"
LOKI_DIR = "/loki"
RULES_DIR = os.path.join(LOKI_DIR, "rules")

logger = logging.getLogger(__name__)


class LokiOperatorCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    _port = 3100
    _name = "loki"

    def __init__(self, *args):
        super().__init__(*args)
        self._container = self.unit.get_container(self._name)
        self._stored.set_default(k8s_service_patched=False, config="")
        self.alertmanager_consumer = AlertmanagerConsumer(self, relation_name="alertmanager")
        self.grafana_source_consumer = GrafanaSourceConsumer(
            charm=self,
            name="grafana-source",
            refresh_event=self.on.loki_pebble_ready,
            source_type="loki",
            source_port=str(self._port),
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.loki_pebble_ready, self._on_loki_pebble_ready)
        self.framework.observe(
            self.alertmanager_consumer.on.cluster_changed, self._on_alertmanager_change
        )
        self.loki_provider = None
        self._loki_server = LokiServer()
        self._provide_loki()

    ##############################################
    #           CHARM HOOKS HANDLERS             #
    ##############################################
    def _on_install(self, _):
        """Handler for the install event during which we will update the K8s service."""
        self._patch_k8s_service()

    def _on_config_changed(self, event):
        self._configure(event)

    def _on_upgrade_charm(self, event):
        self._patch_k8s_service()
        self._configure(event)

    def _on_loki_pebble_ready(self, event):
        self._configure(event)

    def _on_alertmanager_change(self, event):
        self._configure(event)

    def _configure(self, event):
        """Configure Loki charm."""
        restart = False

        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return False

        current_layer = self._container.get_plan().services
        new_layer = self._build_pebble_layer

        if current_layer != new_layer:
            restart = True

        config = self._loki_config()

        try:
            if yaml.safe_load(self._stored.config) != config:
                config_as_yaml = yaml.safe_dump(config)
                self._container.push(LOKI_CONFIG, config_as_yaml)
                logger.info("Pushed new configuration")
                self._stored.config = config_as_yaml
                restart = True
        except (ProtocolError, PathError) as e:
            self.unit.status = BlockedStatus(str(e))
            return False

        if restart:
            self._container.add_layer(self._name, new_layer, combine=True)
            self._container.restart(self._name)
            logger.info("Loki (re)started")

        self.unit.status = ActiveStatus()

    @property
    def _loki_command(self):
        """Construct command to launch Loki.

        Returns:
            a string consisting of Loki command and associated
            command line options.
        """
        return f"/usr/bin/loki -config.file={LOKI_CONFIG}"

    @property
    def _build_pebble_layer(self):
        """Construct the pebble layer.

        Returns:
            a Pebble layer specification for the Loki workload container.
        """
        pebble_layer = {
            "summary": "Loki layer",
            "description": "pebble config layer for Loki",
            "services": {
                "loki": {
                    "override": "replace",
                    "summary": "loki",
                    "command": self._loki_command,
                    "startup": "enabled",
                },
            },
        }

        return pebble_layer

    ##############################################
    #             UTILITY METHODS                #
    ##############################################
    def _provide_loki(self):
        """Gets LokiPushApiProvider instance into `self.loki_provider`."""
        try:
            version = self._loki_server.version
            self.loki_provider = self.loki_provider or LokiPushApiProvider(self)
            logger.debug("Loki Provider is available. Loki version: %s", version)
        except LokiServerNotReadyError as e:
            self.unit.status = WaitingStatus(str(e))
        except LokiServerError as e:
            self.unit.status = BlockedStatus(str(e))

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

    def _alerting_config(self) -> str:
        """Construct Loki altering configuration.

        Returns:
            a string consisting of comma-separated list of Alertmanager URLs
            to send notifications to.
        """
        alerting_config = ""
        alertmanagers = self.alertmanager_consumer.get_cluster_info()

        if not alertmanagers:
            logger.debug("No alertmanagers available")
            return alerting_config

        return ",".join([f"http://{am}" for am in alertmanagers])

    def _loki_config(self) -> dict:
        """Construct Loki configuration.

        Some minimal configuration is required for Loki to start, including: storage paths, schema,
        ring.

        Returns:
            Dictionary representation of the Loki YAML config
        """
        config = textwrap.dedent(
            f"""
            target: all
            auth_enabled: false

            server:
              http_listen_port: {self._port}

            common:
              path_prefix: {LOKI_DIR}
              storage:
                filesystem:
                  chunks_directory: {os.path.join(LOKI_DIR, "chunks")}
                  rules_directory: {RULES_DIR}
              replication_factor: 1
              ring:
                instance_addr: {self.loki_provider.unit_ip if self.loki_provider else ""}
                kvstore:
                  store: inmemory

            schema_config:
              configs:
                - from: 2020-10-24
                  store: boltdb-shipper
                  object_store: filesystem
                  schema: v11
                  index:
                    prefix: index_
                    period: 24h

            ruler:
              alertmanager_url: {self._alerting_config()}
        """
        )
        return yaml.safe_load(config)


if __name__ == "__main__":
    main(LokiOperatorCharm)
