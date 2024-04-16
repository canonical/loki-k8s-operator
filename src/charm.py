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
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast
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
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.observability_libs.v1.cert_handler import CertHandler
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
from ops import CollectStatusEvent, StoredState
from ops.charm import CharmBase
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    Port,
    StatusBase,
    WaitingStatus,
)
from ops.pebble import Error, Layer, PathError, ProtocolError

# To keep a tidy debug-log, we suppress some DEBUG/INFO logs from some imported libs,
# even when charm logging is set to a lower level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class CompositeStatus(TypedDict):
    """Per-component status holder."""

    # These are going to go into stored state, so we must use marshallable objects.
    # They are passed to StatusBase.from_name().
    k8s_patch: Tuple[str, str]
    config: Tuple[str, str]
    rules: Tuple[str, str]


def to_tuple(status: StatusBase) -> Tuple[str, str]:
    """Convert a StatusBase to tuple, so it is marshallable into StoredState."""
    return status.name, status.message


def to_status(tpl: Tuple[str, str]) -> StatusBase:
    """Convert a tuple to a StatusBase, so it could be used natively with ops."""
    name, message = tpl
    return StatusBase.from_name(name, message)


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

    _stored = StoredState()
    _port = HTTP_LISTEN_PORT
    _name = "loki"
    _ca_cert_path = "/usr/local/share/ca-certificates/cos-ca.crt"

    def __init__(self, *args):
        super().__init__(*args)

        # We need stored state for push statuses.
        # https://discourse.charmhub.io/t/its-probably-ok-for-a-unit-to-go-into-error-state/13022
        self._stored.set_default(
            status=CompositeStatus(
                k8s_patch=to_tuple(ActiveStatus()),
                config=to_tuple(ActiveStatus()),
                rules=to_tuple(ActiveStatus()),
            )
        )

        self._loki_container = self.unit.get_container(self._name)
        self._node_exporter_container = self.unit.get_container("node-exporter")
        self.unit.open_port(protocol="tcp", port=self._port)

        # If Loki is run in single-tenant mode, all the chunks are put in a folder named "fake"
        # https://grafana.com/docs/loki/latest/operations/storage/filesystem/
        # https://grafana.com/docs/loki/latest/rules/#ruler-storage
        tenant_id = "fake"
        self.rules_dir_tenant = os.path.join(RULES_DIR, tenant_id)

        self.unit.set_ports(Port("tcp", self._port))

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            self._loki_container.name,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.server_cert = CertHandler(
            self,
            key="loki-server-cert",
            sans=[self.hostname],
        )
        # Update certs here in init to avoid code ordering issues
        self._update_cert()
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
            scheme=lambda: "https" if self._certs_on_disk else "http",
            strip_prefix=True,
        )
        self.framework.observe(self.ingress_per_unit.on.ready_for_unit, self._on_ingress_changed)
        self.framework.observe(self.ingress_per_unit.on.revoked_for_unit, self._on_ingress_changed)

        self.grafana_source_provider = GrafanaSourceProvider(
            charm=self,
            refresh_event=[
                self.on.loki_pebble_ready,
                self.server_cert.on.cert_changed,
            ],
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
                self.server_cert.on.cert_changed,
            ],
        )

        external_url = urlparse(self._external_url)
        self.loki_provider = LokiPushApiProvider(
            self,
            address=external_url.hostname or self.hostname,
            port=external_url.port or 443 if self._certs_on_disk else 80,
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
            self.on.node_exporter_pebble_ready, self._on_node_exporter_pebble_ready
        )

        self.framework.observe(
            self.loki_provider.on.loki_push_api_alert_rules_changed,
            self._loki_push_api_alert_rules_changed,
        )
        self.framework.observe(self.on.logging_relation_changed, self._on_logging_relation_changed)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    ##############################################
    #           CHARM HOOKS HANDLERS             #
    ##############################################

    def _on_collect_unit_status(self, event: CollectStatusEvent):
        # "Pull" statuses
        # TODO refactor _configure to turn the "rules" status into a "pull" status.

        # "Push" statuses
        for status in self._stored.status.values():
            event.add_status(to_status(status))

    def _on_config_changed(self, _):
        self._configure()

    def _on_upgrade_charm(self, _):
        self._configure()

    def _on_server_cert_changed(self, _):
        self._update_cert()
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

    def _on_node_exporter_pebble_ready(self, _):
        current_layer = self._node_exporter_container.get_plan()
        new_layer = self._node_exporter_pebble_layer
        restart = current_layer.services != new_layer.services

        if restart:
            self._node_exporter_container.add_layer("node-exporter", new_layer, combine=True)
            self._node_exporter_container.restart("node-exporter")
            logger.info("Node Exporter (re)started")

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
    def _node_exporter_pebble_layer(self) -> Layer:
        """Construct the pebble layer.

        Returns:
            a Pebble layer specification for the Loki workload container.
        """
        pebble_layer = Layer(
            {
                "summary": "Node Exporter layer",
                "description": "pebble config layer for Node Exporter",
                "services": {
                    "node-exporter": {
                        "override": "replace",
                        "summary": "node exporter",
                        "command": "/bin/node_exporter",
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
        scheme = "https" if self.server_cert.server_cert else "http"
        return f"{scheme}://{self.hostname}:{self._port}"

    @property
    def scrape_jobs(self) -> List[Dict[str, Any]]:
        """Loki and node exporter scrape jobs."""
        return self.loki_scrape_jobs + self.node_exporter_scrape_jobs

    @property
    def loki_scrape_jobs(self) -> List[Dict[str, Any]]:
        """Generate scrape jobs.

        Note: We're generating a scrape job for the leader only because loki is not intended to
        be scaled beyond one unit. If we wanted to scrape all potential units, we would need
        to collect all the peer addresses over peer relation data.
        """
        job: Dict[str, Any] = {"static_configs": [{"targets": [f"{self.hostname}:{self._port}"]}]}

        if self._certs_on_disk:
            job["scheme"] = "https"

        return [job]

    @property
    def node_exporter_scrape_jobs(self) -> List[Dict[str, Any]]:
        """Generate scrape jobs for the node exporter."""
        job: Dict[str, Any] = {"static_configs": [{"targets": [f"{self.hostname}:9100"]}]}
        return [job]

    @property
    def _certs_on_disk(self) -> bool:
        """Check if the TLS setup is ready on disk."""
        return (
            self._loki_container.can_connect()
            and self._loki_container.exists(CERT_FILE)
            and self._loki_container.exists(KEY_FILE)
        )

    @property
    def _certs_in_reldata(self) -> bool:
        """Check if the certificate is available in relation data."""
        return (
            self.server_cert.enabled
            and (self.server_cert.server_cert is not None)
            and (self.server_cert.private_key is not None)
            and (self.server_cert.ca_cert is not None)
        )

    ##############################################
    #             UTILITY METHODS                #
    ##############################################
    def _configure(self):  # noqa: C901
        """Configure Loki charm."""
        # "is_ready" is a racy check, so we do it once here (instead of in collect-status)
        if self.resources_patch.is_ready():
            self._stored.status["k8s_patch"] = to_tuple(ActiveStatus())
        else:
            if isinstance(to_status(self._stored.status["k8s_patch"]), ActiveStatus):
                self._stored.status["k8s_patch"] = to_tuple(
                    WaitingStatus("Waiting for resource limit patch to apply")
                )

        # "can_connect" is a racy check, so we do it once here (instead of in collect-status)
        if self._loki_container.can_connect():
            self._stored.status["config"] = to_tuple(ActiveStatus())
        else:
            self._stored.status["config"] = to_tuple(MaintenanceStatus("Configuring Loki"))
            return

        current_layer = self._loki_container.get_plan()
        new_layer = self._build_pebble_layer
        restart = current_layer.services != new_layer.services

        config = ConfigBuilder(
            instance_addr=self.hostname,
            alertmanager_url=self._alerting_config(),
            external_url=self._external_url,
            ingestion_rate_mb=int(self.config["ingestion-rate-mb"]),
            ingestion_burst_size_mb=int(self.config["ingestion-burst-size-mb"]),
            http_tls=(self.server_cert.server_cert is not None),
        ).build()

        # At this point we're already after the can_connect guard, so if the following pebble operations fail, better
        # to let the charm go into error state than setting blocked.
        if self._certs_in_reldata and not self._certs_on_disk:
            self._update_cert()
        restart = self._update_config(config) or restart

        if restart:
            self._loki_container.add_layer(self._name, new_layer, combine=True)
            self._loki_container.restart(self._name)
            logger.info("Loki (re)started")

        if isinstance(to_status(self._stored.status["rules"]), BlockedStatus):
            # Wait briefly for Loki to come back up and re-check the alert rules
            # in case an upgrade/refresh caused the check to occur when it wasn't
            # ready yet. TODO: use custom pebble notice for "workload ready" event.
            time.sleep(2)
            self._check_alert_rules()
            return  # TODO: why do we have a return here?

        self.ingress_per_unit.provide_ingress_requirements(
            scheme="https" if self._certs_on_disk else "http", port=self._port
        )
        self.metrics_provider.update_scrape_job_spec(self.scrape_jobs)
        self.grafana_source_provider.update_source(source_url=self._external_url)
        self.loki_provider.update_endpoint(url=self._external_url)
        self.catalogue.update_item(item=self._catalogue_item)

    def _update_config(self, config: dict) -> bool:
        if self._running_config() != config:
            config_as_yaml = yaml.safe_dump(config)
            self._loki_container.push(LOKI_CONFIG, config_as_yaml, make_dirs=True)
            logger.info("Pushed new configuration")
            return True

        return False

    def _update_cert(self):
        if not self._loki_container.can_connect():
            return

        ca_cert_path = Path(self._ca_cert_path)

        if self._certs_in_reldata:
            # Save the workload certificates
            self._loki_container.push(
                CERT_FILE,
                self.server_cert.server_cert,  # pyright: ignore
                make_dirs=True,
            )
            self._loki_container.push(
                KEY_FILE,
                self.server_cert.private_key,  # pyright: ignore
                make_dirs=True,
            )
            # Save the CA among the trusted CAs and trust it
            self._loki_container.push(
                ca_cert_path,
                self.server_cert.ca_cert,  # pyright: ignore
                make_dirs=True,
            )

            # Repeat for the charm container. We need it there for loki client requests.
            ca_cert_path.parent.mkdir(exist_ok=True, parents=True)
            ca_cert_path.write_text(self.server_cert.ca_cert)  # pyright: ignore
        else:
            self._loki_container.remove_path(CERT_FILE, recursive=True)
            self._loki_container.remove_path(KEY_FILE, recursive=True)
            self._loki_container.remove_path(ca_cert_path, recursive=True)

            # Repeat for the charm container.
            ca_cert_path.unlink(missing_ok=True)

        self._loki_container.exec(["update-ca-certificates", "--fresh"]).wait()
        subprocess.run(["update-ca-certificates", "--fresh"])

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
        if not self._loki_container.can_connect():
            return {}

        try:
            return yaml.safe_load(self._loki_container.pull(LOKI_CONFIG, encoding="utf-8").read())
        except (FileNotFoundError, Error):
            return {}

    def _loki_push_api_alert_rules_changed(self, _: LokiPushApiAlertRulesChanged) -> None:
        """Perform all operations needed to keep alert rules in the right status."""
        if self._ensure_alert_rules_path():
            self._regenerate_alert_rules()

            # Don't try to configure if checking the rules left us in BlockedStatus
            if isinstance(to_status(self._stored.status["rules"]), ActiveStatus):
                self._configure()

    def _ensure_alert_rules_path(self) -> bool:
        """Ensure that the workload container has the appropriate directory structure."""
        # create tenant dir so that the /loki/api/v1/rules endpoint returns "no rule groups found"
        # instead of "unable to read rule dir /loki/rules/fake: no such file or directory"
        if self._loki_container.can_connect():
            try:
                self._loki_container.make_dir(self.rules_dir_tenant, make_parents=True)
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

        if self._loki_container.can_connect():
            for filename, content in file_mappings.items():
                path = os.path.join(self.rules_dir_tenant, filename)
                self._loki_container.push(path, content, make_dirs=True)
        logger.debug("Saved alert rules to disk")

    def _remove_alert_rules_files(self) -> None:
        """Remove alert rules files from workload container."""
        if not self._loki_container.can_connect():
            logger.debug("Cannot connect to container to remove alert rule files!")
            return

        files = self._loki_container.list_files(self.rules_dir_tenant)
        for f in files:
            self._loki_container.remove_path(f.path)

    @property
    def _internal_url(self) -> str:
        """Return the fqdn dns-based in-cluster (private) address of the loki api server."""
        scheme = "https" if self._certs_on_disk else "http"
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
                self._stored.status["rules"] = to_tuple(BlockedStatus(log_msg))
                return

            message = "{} - {}".format(e.code, e.msg)  # type: ignore
            logger.error("Checking alert rules: %s", message)
            self._stored.status["rules"] = to_tuple(
                BlockedStatus("Errors in alert rule groups. Check juju debug-log")
            )
            return
        except URLError as e:
            logger.error("Checking alert rules: %s", e.reason)
            self._stored.status["rules"] = to_tuple(
                BlockedStatus("Error connecting to Loki. Check juju debug-log")
            )
            return
        except Exception as e:
            logger.error("Checking alert rules: %s", e)
            self._stored.status["rules"] = to_tuple(
                BlockedStatus("Error connecting to Loki. Check juju debug-log")
            )
            return
        else:
            logger.debug("Checking alert rules: Ok")
            self._stored.status["rules"] = to_tuple(ActiveStatus())
            return

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {
            "cpu": self.model.config.get("cpu"),
            "memory": self.model.config.get("memory"),
        }
        requests = {"cpu": "0.25", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    def _on_k8s_patch_failed(self, event: K8sResourcePatchFailedEvent):
        self._stored.status["k8s_patch"] = to_tuple(BlockedStatus(cast(str, event.message)))

    @property
    def _loki_version(self) -> Optional[str]:
        """Returns the version of Loki.

        Returns:
            A string equal to the Loki version
        """
        if not self._loki_container.can_connect():
            return None
        version_output, _ = self._loki_container.exec(["/usr/bin/loki", "-version"]).wait_output()
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
