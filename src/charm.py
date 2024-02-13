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
import ssl
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

import yaml
from charms.alertmanager_k8s.v1.alertmanager_dispatch import AlertmanagerConsumer
from charms.catalogue_k8s.v1.catalogue import CatalogueConsumer, CatalogueItem
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.grafana_k8s.v0.grafana_source import GrafanaSourceProvider
from charms.loki_k8s.v0.loki_push_api import (
    LokiPushApiAlertRulesChanged,
    LokiPushApiProvider,
)
from charms.observability_libs.v0.cert_handler import CertHandler
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_k8s.v1.charm_tracing import trace_charm
from charms.tempo_k8s.v1.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v1.ingress_per_unit import IngressPerUnitRequirer
from config_builder import (
    CERT_FILE,
    HTTP_LISTEN_PORT,
    KEY_FILE,
    LOKI_CONFIG,
    RULES_DIR,
    ConfigBuilder,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import ChangeError, Error, Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)


@trace_charm(
    tracing_endpoint="tracing_endpoint",
    server_cert="server_cert_path",
    extra_types=[
        GrafanaDashboardProvider,
        GrafanaSourceProvider,
        LokiPushApiProvider,
        CertHandler,
        ConfigBuilder,
        MetricsEndpointProvider,
    ],
)
class LokiOperatorCharm(CharmBase):
    """Charm the service."""

    _port = HTTP_LISTEN_PORT
    _name = "loki"
    _ca_cert_path = "/usr/local/share/ca-certificates/cos-ca.crt"

    def __init__(self, *args):
        super().__init__(*args)
        self._container = self.unit.get_container(self._name)

        # If Loki is run in single-tenant mode, all the chunks are put in a folder named "fake"
        # https://grafana.com/docs/loki/latest/operations/storage/filesystem/
        # https://grafana.com/docs/loki/latest/rules/#ruler-storage
        tenant_id = "fake"
        self.rules_dir_tenant = os.path.join(RULES_DIR, tenant_id)

        self.service_patch = KubernetesServicePatch(
            self, [ServicePort(self._port, name=self.app.name)]
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            self._container.name,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.server_cert = CertHandler(
            self,
            key="loki-server-cert",
            peer_relation_name="replicas",
            extra_sans_dns=[self.hostname],
        )
        self.framework.observe(
            self.server_cert.on.cert_changed,  # pyright: ignore
            self._on_server_cert_changed,
        )

        self.framework.observe(self.resources_patch.on.patch_failed, self._on_k8s_patch_failed)

        self.alertmanager_consumer = AlertmanagerConsumer(self, relation_name="alertmanager")
        self.framework.observe(
            self.alertmanager_consumer.on.cluster_changed, self._on_alertmanager_change
        )

        self.ingress_per_unit = IngressPerUnitRequirer(
            self,
            relation_name="ingress",
            port=self._port,
            scheme=lambda: "https" if self._tls_ready else "http",
            strip_prefix=True,
        )
        self.framework.observe(self.ingress_per_unit.on.ready_for_unit, self._on_ingress_changed)
        self.framework.observe(self.ingress_per_unit.on.revoked_for_unit, self._on_ingress_changed)

        self.grafana_source_provider = GrafanaSourceProvider(
            charm=self,
            refresh_event=self.on.loki_pebble_ready,
            source_type="loki",
            source_url=self._external_url,
        )

        self.metrics_provider = MetricsEndpointProvider(
            self,
            jobs=self.scrape_jobs,
            refresh_event=[
                self.on.update_status,
                self.ingress_per_unit.on.ready_for_unit,
                self.ingress_per_unit.on.revoked_for_unit,
                self.on.ingress_relation_departed,
            ],
        )

        external_url = urlparse(self._external_url)
        self.loki_provider = LokiPushApiProvider(
            self,
            address=external_url.hostname or self.hostname,
            port=external_url.port or 443 if self._tls_ready else 80,
            scheme=external_url.scheme,
            path=f"{external_url.path}/loki/api/v1/push",
        )

        self.dashboard_provider = GrafanaDashboardProvider(self)

        self.catalogue = CatalogueConsumer(charm=self, item=self._catalogue_item)
        self.tracing = TracingEndpointRequirer(self)

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

    def _update_ca_certs(self):
        # Charm container
        ca_cert_path = Path(self._ca_cert_path)
        if self.server_cert.ca:
            ca_cert_path.parent.mkdir(exist_ok=True, parents=True)
            ca_cert_path.write_text(self.server_cert.ca)  # pyright: ignore
        else:
            ca_cert_path.unlink(missing_ok=True)

    def _on_server_cert_changed(self, _):
        self._update_ca_certs()  # Will go into error state if not can_connect, and that's ok
        self._configure()

    def _on_loki_pebble_ready(self, _):
        if self._ensure_alert_rules_path():
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

    def _on_logging_relation_changed(self, event):
        # If there is a change in logging relation, let's update Loki endpoint
        # We are listening to relation_change to handle the Loki scale down to 0 and scale up again
        # when it is related with ingress. If not, endpoints will end up outdated in consumer side.
        self.loki_provider.update_endpoint(url=self._external_url, relation=event.relation)

    ##############################################
    #                 PROPERTIES                 #
    ##############################################

    @property
    def _catalogue_item(self) -> CatalogueItem:
        return CatalogueItem(
            name="Loki",
            icon="math-log",
            # Loki does not have a flashy web UI but something is better than nothing
            # https://grafana.com/docs/loki/latest/reference/api/
            url=f"{self._external_url}/services",
            description=(
                "Loki collects, stores and serves logs, "
                "alongside optional key-value pairs called labels."
            ),
        )

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
        scheme = "https" if self.server_cert.cert else "http"
        return f"{scheme}://{self.hostname}:{self._port}"

    @property
    def scrape_jobs(self) -> List[Dict[str, Any]]:
        """Generate scrape jobs.

        Note: We're generating a scrape job for the leader only because loki is not intended to
        be scaled beyond one unit. If we wanted to scrape all potential units, we would need
        to collect all the peer addresses over peer relation data.
        """
        job: Dict[str, Any] = {"static_configs": [{"targets": [f"{self.hostname}:{self._port}"]}]}

        if self._tls_ready:
            job["scheme"] = "https"

        return [job]

    @property
    def _tls_ready(self) -> bool:
        return (
            self._container.can_connect()
            and self._container.exists(CERT_FILE)
            and self._container.exists(KEY_FILE)
        )

    ##############################################
    #             UTILITY METHODS                #
    ##############################################
    def _configure(self):  # noqa: C901
        """Configure Loki charm."""
        if not self.resources_patch.is_ready():
            if isinstance(self.unit.status, ActiveStatus) or self.unit.status.message == "":
                self.unit.status = WaitingStatus("Waiting for resource limit patch to apply")
            return

        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        current_layer = self._container.get_plan()
        new_layer = self._build_pebble_layer
        restart = current_layer.services != new_layer.services

        config = ConfigBuilder(
            instance_addr=self.hostname,
            alertmanager_url=self._alerting_config(),
            external_url=self._external_url,
            ingestion_rate_mb=int(self.config["ingestion-rate-mb"]),
            ingestion_burst_size_mb=int(self.config["ingestion-burst-size-mb"]),
            http_tls=(self.server_cert.cert is not None),
        ).build()

        try:
            self._push_certs()
            restart = restart or self._update_config(config)
        except (ProtocolError, PathError) as e:
            self.unit.status = BlockedStatus(str(e))
            return
        except Exception as e:
            self.unit.status = BlockedStatus(str(e))
            return

        if restart:
            try:
                self._container.add_layer(self._name, new_layer, combine=True)
                self._container.restart(self._name)
                logger.info("Loki (re)started")
            except ChangeError as e:
                msg = f"Failed to restart loki: {e}"  # or e.err?
                self.unit.status = BlockedStatus(msg)
                logger.error(msg)
                return

        # Don't clear alert error states on reconfigure
        # but let errors connecting clear after a restart
        if (
            isinstance(self.unit.status, BlockedStatus)
            and "Errors in alert rule" in self.unit.status.message
        ):
            # Wait briefly for Loki to come back up and re-check the alert rules
            # in case an upgrade/refresh caused the check to occur when it wasn't
            # ready yet
            time.sleep(2)
            self._check_alert_rules()
            return

        self.ingress_per_unit.provide_ingress_requirements(
            scheme="https" if self._tls_ready else "http", port=self._port
        )
        self.metrics_provider.update_scrape_job_spec(self.scrape_jobs)
        self.grafana_source_provider.update_source(source_url=self._external_url)
        self.loki_provider.update_endpoint(url=self._external_url)
        self.catalogue.update_item(item=self._catalogue_item)

        self.unit.status = ActiveStatus()

    def _update_config(self, config: dict) -> bool:
        if self._running_config() != config:
            config_as_yaml = yaml.safe_dump(config)
            self._container.push(LOKI_CONFIG, config_as_yaml, make_dirs=True)
            logger.info("Pushed new configuration")
            return True

        return False

    def _push_certs(self):
        self._container.remove_path(CERT_FILE, recursive=True)
        self._container.remove_path(KEY_FILE, recursive=True)

        if self.server_cert.cert:
            self._container.push(CERT_FILE, self.server_cert.cert, make_dirs=True)

        if self.server_cert.key:
            self._container.push(KEY_FILE, self.server_cert.key, make_dirs=True)

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

        return ",".join(alertmanagers)

    def _running_config(self) -> Dict[str, Any]:
        """Get the on-disk Loki config."""
        if not self._container.can_connect():
            return {}

        try:
            return yaml.safe_load(self._container.pull(LOKI_CONFIG, encoding="utf-8").read())
        except (FileNotFoundError, Error):
            return {}

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
                self._container.make_dir(self.rules_dir_tenant, make_parents=True)
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
                path = os.path.join(self.rules_dir_tenant, filename)
                self._container.push(path, content, make_dirs=True)
        logger.debug("Saved alert rules to disk")

    def _remove_alert_rules_files(self) -> None:
        """Remove alert rules files from workload container."""
        if not self._container.can_connect():
            logger.debug("Cannot connect to container to remove alert rule files!")
            return

        files = self._container.list_files(self.rules_dir_tenant)
        for f in files:
            self._container.remove_path(f.path)

    @property
    def _internal_url(self) -> str:
        """Return the fqdn dns-based in-cluster (private) address of the loki api server."""
        scheme = "https" if self._tls_ready else "http"
        return f"{scheme}://{socket.getfqdn()}:{self._port}"

    def _check_alert_rules(self):
        """Check alert rules using Loki API."""
        ssl_context = ssl.create_default_context(
            cafile=self._ca_cert_path if Path(self._ca_cert_path).exists() else None,
        )
        url = f"{self._internal_url}/loki/api/v1/rules"
        try:
            logger.debug(f"Checking loki alert rules via {url}.")
            urllib.request.urlopen(url, timeout=2.0, context=ssl_context)
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
        self.unit.status = BlockedStatus(str(event.message))

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

    @property
    def tracing_endpoint(self) -> Optional[str]:
        """Tempo endpoint for charm tracing."""
        return self.tracing.otlp_http_endpoint()

    @property
    def server_cert_path(self) -> Optional[str]:
        """Server certificate path for TLS tracing."""
        return CERT_FILE


if __name__ == "__main__":
    # We need use_juju_for_storage=True because ingress_per_unit
    # requires it to keep track of the ingress address.
    main(LokiOperatorCharm, use_juju_for_storage=True)
