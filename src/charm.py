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
from urllib.parse import urlparse

import yaml
from charms.alertmanager_k8s.v0.alertmanager_dispatch import AlertmanagerConsumer
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceProvider
from charms.loki_k8s.v0.loki_push_api import (
    LokiPushApiAlertRulesChanged,
    LokiPushApiProvider,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.traefik_k8s.v0.ingress_per_unit import IngressPerUnitRequirer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import PathError, ProtocolError

from loki_server import LokiServer, LokiServerError, LokiServerNotReadyError

# Paths in workload container
LOKI_CONFIG = "/etc/loki/local-config.yaml"
LOKI_DIR = "/loki"
RULES_DIR = os.path.join(LOKI_DIR, "rules")
PEER = "loki"

logger = logging.getLogger(__name__)


class LokiOperatorCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    _port = 3100
    _name = PEER

    def __init__(self, *args):
        super().__init__(*args)
        self._container = self.unit.get_container(self._name)
        self._stored.set_default(k8s_service_patched=False, config="")
        self.service_patch = KubernetesServicePatch(self, [(self.app.name, self._port)])
        self.alertmanager_consumer = AlertmanagerConsumer(self, relation_name="alertmanager")
        self.ingress_per_unit = IngressPerUnitRequirer(
            self, endpoint="ingress-per-unit", port=self._port
        )
        external_url = urlparse(self._external_url)
        self.grafana_source_provider = GrafanaSourceProvider(
            charm=self,
            refresh_event=self.on.loki_pebble_ready,
            source_type=PEER,
            source_url=self._external_url,
        )

        self.loki_provider = LokiPushApiProvider(
            self,
            address=external_url.hostname or "",
            port=external_url.port or self._port,
            scheme=external_url.scheme,
            path=f"{external_url.path}/loki/api/v1/push",
        )

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.loki_pebble_ready, self._on_loki_pebble_ready)
        self.framework.observe(
            self.alertmanager_consumer.on.cluster_changed, self._on_alertmanager_change
        )
        self.framework.observe(
            self.loki_provider.on.loki_push_api_alert_rules_changed,
            self._loki_push_api_alert_rules_changed,
        )
        self.framework.observe(self.ingress_per_unit.on.ingress_changed, self._on_ingress_changed)

        self._loki_server = LokiServer()
        self._provide_loki()

    ##############################################
    #           CHARM HOOKS HANDLERS             #
    ##############################################
    def _on_config_changed(self, event):
        self._configure(event)

    def _on_upgrade_charm(self, event):
        self._configure(event)

    def _on_loki_pebble_ready(self, event):
        self._configure(event)

    def _on_alertmanager_change(self, event):
        self._configure(event)

    def _loki_push_api_alert_rules_changed(self, event):
        self._configure(event)

    def _on_ingress_changed(self, event):
        self._configure(event)
        self.loki_provider.update_endpoint()

    def _configure(self, event):
        """Configure Loki charm."""
        restart = False

        if isinstance(event, LokiPushApiAlertRulesChanged) and event.error:
            self.unit.status = BlockedStatus(event.message)
            return False

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

        self.grafana_source_provider.update_source(self._external_url)
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
            logger.debug("Loki Provider is available. Loki version: %s", version)
        except LokiServerNotReadyError as e:
            self.unit.status = WaitingStatus(str(e))
        except LokiServerError as e:
            self.unit.status = BlockedStatus(str(e))

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
        external_url = urlparse(self._external_url)
        no_path = "''"
        config = textwrap.dedent(
            f"""
            target: all
            auth_enabled: false

            server:
              http_listen_port: {self._port}
              http_listen_address: 0.0.0.0
              http_path_prefix: {external_url.path if external_url.path else no_path}
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

    @property
    def _hostname(self) -> str:
        """Unit's hostname."""
        return "{}-{}.{}-endpoints.{}.svc.cluster.local".format(
            self.app.name,
            self.unit.name.split("/")[-1],
            self.app.name,
            self.model.name,
        )

    @property
    def _external_url(self) -> str:
        """Return the external hostname to be passed to ingress via the relation."""
        if ingress_url := self.ingress_per_unit.url:
            logger.debug("This unit's ingress URL: %s", ingress_url)
            return ingress_url

        # If we do not have an ingress, then use the pod ip as hostname.
        # The reason to prefer this over the pod name (which is the actual
        # hostname visible from the pod) or a K8s service, is that those
        # are routable virtually exclusively inside the cluster (as they rely)
        # on the cluster's DNS service, while the ip address is _sometimes_
        # routable from the outside, e.g., when deploying on MicroK8s on Linux.
        return f"http://{self._hostname}:{self._port}"


if __name__ == "__main__":
    main(LokiOperatorCharm)
