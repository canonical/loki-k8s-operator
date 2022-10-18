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
import re
import socket
import textwrap
from typing import Optional
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

import yaml
from charms.alertmanager_k8s.v0.alertmanager_dispatch import AlertmanagerConsumer
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceProvider
from charms.loki_k8s.v0.loki_push_api import (
    LokiPushApiAlertRulesChanged,
    LokiPushApiProvider,
)
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.traefik_k8s.v1.ingress_per_unit import IngressPerUnitRequirer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer, PathError, ProtocolError

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

        # If Loki is run in single-tenant mode, all the chunks are put in a folder named "fake"
        # https://grafana.com/docs/loki/latest/operations/storage/filesystem/
        # https://grafana.com/docs/loki/latest/rules/#ruler-storage
        tenant_id = "fake"
        self._rules_dir = os.path.join(RULES_DIR, tenant_id)

        self.service_patch = KubernetesServicePatch(self, [(self.app.name, self._port)])

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            self._container.name,
            resource_reqs_func=self._resource_reqs_from_config,
        )
        self.framework.observe(self.resources_patch.on.patch_failed, self._on_k8s_patch_failed)

        self.alertmanager_consumer = AlertmanagerConsumer(self, relation_name="alertmanager")
        self.framework.observe(
            self.alertmanager_consumer.on.cluster_changed, self._on_alertmanager_change
        )

        self.ingress_per_unit = IngressPerUnitRequirer(
            self, relation_name="ingress", port=self._port
        )
        self.framework.observe(self.ingress_per_unit.on.ready_for_unit, self._on_ingress_changed)
        self.framework.observe(self.ingress_per_unit.on.revoked_for_unit, self._on_ingress_changed)

        self.grafana_source_provider = GrafanaSourceProvider(
            charm=self,
            refresh_event=self.on.loki_pebble_ready,
            source_type="loki",
            source_url=self._external_url,
        )
        scrape_jobs = [{"static_configs": [{"targets": [f"*:{self._port}"]}]}]
        self.metrics_provider = MetricsEndpointProvider(self, jobs=scrape_jobs)

        self._loki_server = LokiServer()
        parsed_external_url = urlparse(self._external_url)

        self.loki_provider = LokiPushApiProvider(
            self,
            address=parsed_external_url.hostname or self.hostname,
            port=parsed_external_url.port or self._port,
            scheme=parsed_external_url.scheme,
            path=f"{parsed_external_url.path}/loki/api/v1/push",
        )

        self.dashboard_provider = GrafanaDashboardProvider(self)

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.loki_pebble_ready, self._on_loki_pebble_ready)

        self.framework.observe(
            self.loki_provider.on.loki_push_api_alert_rules_changed,
            self._loki_push_api_alert_rules_changed,
        )
        self.framework.observe(self.on.logging_relation_changed, self._on_logging_relation_changed)

    ##############################################
    #           CHARM HOOKS HANDLERS             #
    ##############################################
    def _on_config_changed(self, _):
        self._configure()

    def _on_upgrade_charm(self, _):
        self._configure()

    def _on_loki_pebble_ready(self, _):
        self._regenerate_alert_rules()
        self._configure()
        version = self._loki_version
        if version is not None:
            self.unit.set_workload_version(version)
        else:
            logger.debug("Cannot set workload version at this time: could not get Loki version.")

    def _on_alertmanager_change(self, _):
        self._configure()

    def _on_ingress_changed(self, _):
        self._configure()
        self.loki_provider.update_endpoint(url=self._external_url)

    def _on_logging_relation_changed(self, event):
        # If there is a change in logging relation, let's update Loki endpoint
        # We are listening to relation_change to handle the Loki scale down to 0 and scale up again
        # when it is related with ingress. If not, endpoints will end up outdated in consumer side.
        self.loki_provider.update_endpoint(url=self._external_url, relation=event.relation)

    ##############################################
    #                 PROPERTIES                 #
    ##############################################

    @property
    def _loki_command(self):
        """Construct command to launch Loki.

        Returns:
            a string consisting of Loki command and associated
            command line options.
        """
        return f"/usr/bin/loki -config.file={LOKI_CONFIG}"

    @property
    def _build_pebble_layer(self) -> Layer:
        """Construct the pebble layer.

        Returns:
            a Pebble layer specification for the Loki workload container.
        """
        pebble_layer = Layer(
            {
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
        )

        return pebble_layer

    @property
    def hostname(self) -> str:
        """Unit's hostname."""
        return socket.getfqdn()

    @property
    def _external_url(self) -> str:
        """Return the external hostname to be passed to ingress via the relation."""
        if ingress_url := self.ingress_per_unit.url:
            logger.debug("This unit's ingress URL: %s", ingress_url)
            return ingress_url

        # If we do not have an ingress, then use the pod hostname.
        # The reason to prefer this over the pod name (which is the actual
        # hostname visible from the pod) or a K8s service, is that those
        # are routable virtually exclusively inside the cluster (as they rely)
        # on the cluster's DNS service, while the ip address is _sometimes_
        # routable from the outside, e.g., when deploying on MicroK8s on Linux.
        return f"http://{self.hostname}:{self._port}"

    ##############################################
    #             UTILITY METHODS                #
    ##############################################
    def _configure(self):  # noqa: C901
        """Configure Loki charm."""
        restart = False

        if not self.resources_patch.is_ready():
            if isinstance(self.unit.status, ActiveStatus) or self.unit.status.message == "":
                self.unit.status = WaitingStatus("Waiting for resource limit patch to apply")
            return

        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        current_layer = self._container.get_plan()
        new_layer = self._build_pebble_layer

        if current_layer.services != new_layer.services:
            restart = True

        config = self._loki_config()

        try:
            if yaml.safe_load(self._stored.config) != config:
                config_as_yaml = yaml.safe_dump(config)
                self._container.push(LOKI_CONFIG, config_as_yaml, make_dirs=True)
                logger.info("Pushed new configuration")
                self._stored.config = config_as_yaml
                restart = True
        except (ProtocolError, PathError) as e:
            self.unit.status = BlockedStatus(str(e))
            return
        except Exception as e:
            self.unit.status = BlockedStatus(str(e))
            return

        if restart:
            self._container.add_layer(self._name, new_layer, combine=True)
            self._container.restart(self._name)
            logger.info("Loki (re)started")

        # Don't clear alert error states on reconfigure
        # but let errors connecting clear after a restart
        if (
            isinstance(self.unit.status, BlockedStatus)
            and "Errors in alert rule" in self.unit.status.message
        ):
            return

        self.unit.status = ActiveStatus()

    def _loki_ready(self) -> bool:
        """Gets LokiPushApiProvider instance into `self.loki_provider`."""
        try:
            version = self._loki_server.version
            logger.debug("Loki Provider is available. Loki version: %s", version)
            return True
        except LokiServerNotReadyError as e:
            self.unit.status = WaitingStatus(str(e))
            return False
        except LokiServerError as e:
            self.unit.status = BlockedStatus(str(e))
            return False

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

        Reference: https://grafana.com/docs/loki/latest/configuration/

        Returns:
            Dictionary representation of the Loki YAML config
        """
        config = textwrap.dedent(
            f"""
            target: all
            auth_enabled: false

            server:
              http_listen_port: {self._port}
              http_listen_address: 0.0.0.0
              http_path_prefix: {urlparse(self._external_url).path}

            common:
              path_prefix: {LOKI_DIR}
              storage:
                filesystem:
                  chunks_directory: {os.path.join(LOKI_DIR, "chunks")}
                  rules_directory: {RULES_DIR}
              replication_factor: 1
              ring:
                instance_addr: {socket.getfqdn() or ""}
                kvstore:
                  store: inmemory

            storage_config:
              boltdb:
                directory: /loki/boltdb-shipper-active
              filesystem:
                directory: /loki/chunks

            schema_config:
              configs:
                - from: 2020-10-24
                  store: boltdb
                  object_store: filesystem
                  schema: v11
                  index:
                    prefix: index_
                    period: 24h

            ingester:
              wal:
                enabled: true
                dir: {os.path.join(LOKI_DIR, "chunks", "wal")}
                flush_on_shutdown: true
            ruler:
              external_url: {self._external_url}
              alertmanager_url: {self._alerting_config()}
        """
        )
        return yaml.safe_load(config)

    def _loki_push_api_alert_rules_changed(self, _: LokiPushApiAlertRulesChanged) -> None:
        """Perform all operations needed to keep alert rules in the right status."""
        if self._ensure_alert_rules_path():
            self._regenerate_alert_rules()

            # Don't try to configure if checking the rules left us in BlockedStatus
            if isinstance(self.unit.status, ActiveStatus):
                self._configure()

    def _ensure_alert_rules_path(self) -> bool:
        """Ensure that the workload container has the appropriate directory structure."""
        # create tenant dir so that the /loki/api/v1/rules endpoint returns "no rule groups found"
        # instead of "unable to read rule dir /loki/rules/fake: no such file or directory"
        if self._container.can_connect():
            try:
                self._container.make_dir(self._rules_dir, make_parents=True)
                return True
            except (FileNotFoundError, ProtocolError, PathError):
                logger.debug("Could not create loki directory.")
                return False
            except Exception as e:
                logger.debug("Could not create loki directory: %s", e)
                return False
        return False

    def _regenerate_alert_rules(self):
        """Recreate all alert rules."""
        self._remove_alert_rules_files()
        # If there aren't any alerts, we can just clean it and move on
        if self.loki_provider.alerts:
            self._generate_alert_rules_files()
            self._check_alert_rules()

    def _generate_alert_rules_files(self) -> None:
        """Generate and upload alert rules files.

        Args:
            container: Container into which alert rules files are going to be uploaded
        """
        file_mappings = {}

        for identifier, alert_rules in self.loki_provider.alerts.items():
            rules = yaml.dump({"groups": alert_rules["groups"]})
            file_mappings["{}_alert.rules".format(identifier)] = rules

        if self._container.can_connect():
            for filename, content in file_mappings.items():
                path = os.path.join(self._rules_dir, filename)
                self._container.push(path, content, make_dirs=True)
        logger.debug("Saved alert rules to disk")

    def _remove_alert_rules_files(self) -> None:
        """Remove alert rules files from workload container."""
        if not self._container.can_connect():
            logger.debug("Cannot connect to container to remove alert rule files!")
            return

        files = self._container.list_files(self._rules_dir)
        for f in files:
            self._container.remove_path(f.path)

    def _check_alert_rules(self):
        """Check alert rules using Loki API."""
        url = "http://127.0.0.1:{}/loki/api/v1/rules".format(self.loki_provider.port)
        req = request.Request(url)
        try:
            request.urlopen(req, timeout=2.0)
        except HTTPError as e:
            msg = e.read().decode("utf-8")

            if e.code == 404 and "no rule groups found" in msg:
                log_msg = "Checking alert rules: No rule groups found"
                logger.debug(log_msg)
                self.unit.status = BlockedStatus(log_msg)
                return

            message = "{} - {}".format(e.code, e.msg)  # type: ignore
            logger.error("Checking alert rules: %s", message)
            self.unit.status = BlockedStatus("Errors in alert rule groups. Check juju debug-log")
            return
        except URLError as e:
            logger.error("Checking alert rules: %s", e.reason)
            self.unit.status = BlockedStatus("Error connecting to Loki. Check juju debug-log")
            return
        except Exception as e:
            logger.error("Checking alert rules: %s", e)
            self.unit.status = BlockedStatus("Error connecting to Loki. Check juju debug-log")
            return
        else:
            log_msg = "Checking alert rules: Ok"
            logger.debug(log_msg)
            if isinstance(self.unit.status, BlockedStatus):
                self.unit.status = ActiveStatus()
                logger.info("Clearing blocked status with successful alert rule check")
            return

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {
            "cpu": self.model.config.get("cpu"),
            "memory": self.model.config.get("memory"),
        }
        requests = {"cpu": "0.25", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    def _on_k8s_patch_failed(self, event: K8sResourcePatchFailedEvent):
        self.unit.status = BlockedStatus(event.message)

    @property
    def _loki_version(self) -> Optional[str]:
        """Returns the version of Loki.

        Returns:
            A string equal to the Loki version
        """
        if not self._container.can_connect():
            return None
        version_output, _ = self._container.exec(["/usr/bin/loki", "-version"]).wait_output()
        # Output looks like this:
        # loki, version 2.4.1 (branch: HEAD, ...
        result = re.search(r"version (\d*\.\d*\.\d*)", version_output)
        if result is None:
            return result
        return result.group(1)


if __name__ == "__main__":
    main(LokiOperatorCharm)
