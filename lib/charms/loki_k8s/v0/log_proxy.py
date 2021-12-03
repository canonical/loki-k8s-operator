#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk


r"""## Overview.

This document explains how to use the two principal objects this library provides:

- `LogProxyProvider`: This object can be used by any charmed operator that needs to act
as a Log Proxy to Loki by implementing the provider side of `loki_push_api` relation interface.
For instance a Grafana agent or Promtail charmed operator that receives logs from a workload
and forward them to Loki.

- `LogProxyConsumer`: This object can be used by any K8s charmed operator that needs to
send log to Loki through a Log Proxy by implementing the consumer side of the `loki_push_api`
relation interface.
Filtering logs in Loki is largely performed on the basis of labels.
In the Juju ecosystem, Juju topology labels are used to uniquely identify the workload that
generates telemetry like logs.
In order to be able to control the labels on the logs pushed this object injects a Pebble layer
that runs Promtail in the workload container, injecting Juju topology labels into the
logs on the fly.

## LogProxyConsumer Library Usage

Let's say that we have a workload charm that produces logs and we need to send those logs to a
workload implementing the `loki_push_api` interface, such as `Loki` or `Grafana Agent`.

Adopting this object in a charmed operator consist of two steps:


1. Use the `LogProxyConsumer` class by instanting it in the `__init__` method of the
   charmed operator:

   ```python
   from charms.loki_k8s.v0.log_proxy import LogProxyConsumer, PromtailDigestError

   ...

       def __init__(self, *args):
           ...
           try:
               self._log_proxy = LogProxyConsumer(
                   charm=self, log_files=LOG_FILES, container_name=PEER
               )
           except PromtailDigestError as e:
               msg = str(e)
               logger.error(msg)
               self.unit.status = BlockedStatus(msg)
   ```

   Note that:

   - `LOG_FILES` is a `list` containing the log files we want to send to `Loki` or
   `Grafana Agent`, for instance:

   ```python
   LOG_FILES = [
       "/var/log/apache2/access.log",
       "/var/log/alternatives.log",
   ]
   ```

   - `container_name` is the name of the container in which the application is running.
      If in the Pod there is only one container, this argument can be avoided.

2. Modify the `metadata.yaml` file to add:

   - The `log_proxy` relation in the `requires` section:
     ```yaml
     requires:
       log_proxy:
         interface: loki_push_api
         optional: true
     ```

Once the library is implemented in a charmed operator and a relation is established with
the charm that implements the `loki_push_api` interface, the library will inject a
Pebble layer that runs Promtail in the workload container to send logs.

The object can raise a `PromtailDigestError` when:

- Promtail binary cannot be downloaded.
- No `container_name` parameter has been specified and the Pod has more than 1 container.
- The sha256 sum mismatch for promtail binary.

that's why in the above example, the instantiation is made in a `try/except` block
to handle these situations conveniently.


## LogProxyProvider Library Usage

This object is meant to be used by any charmed operator that needs to act
as a Log Proxy to Loki by implementing the provider side of `log_proxy` relation interface.
For instance a Grafana agent or Promtail charmed operator that receives logs from a workload
and forward them to Loki.

Adopting this object in a charmed operator consist of two steps:

1. Use the `LogProxyProvider` class by instanting it in the `__init__` method of the
   charmed operator:

   ```python
   from charms.loki_k8s.v0.loki_push_api import LogProxyProvider

   ...

       def __init__(self, *args):
           ...
           self._log_proxy = LogProxyProvider(self)
   ```

2. Modify the `metadata.yaml` file to add:

   - The `log_proxy` relation in the `provider` section:
     ```yaml
     provides:
       log_proxy:
         interface: loki_push_api
     ```
"""

import json
import logging
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

import yaml
from ops.charm import CharmBase, RelationChangedEvent, RelationDepartedEvent
from ops.framework import Object, StoredState
from ops.model import ModelError

logger = logging.getLogger(__name__)

# The unique Charmhub library identifier, never change it
LIBID = "a40e938dea5a42eb88b6c76fa6592c4a"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PROMTAIL_BINARY_ZIP_URL = (
    "https://github.com/grafana/loki/releases/download/v2.4.1/promtail-linux-amd64.zip"
)
# Paths in `charm` container
BINARY_DIR = "/tmp"
BINARY_ZIP_FILE_NAME = "promtail-linux-amd64.zip"
BINARY_ZIP_PATH = "{}/{}".format(BINARY_DIR, BINARY_ZIP_FILE_NAME)
BINARY_FILE_NAME = "promtail-linux-amd64"
BINARY_PATH = "{}/{}".format(BINARY_DIR, BINARY_FILE_NAME)
BINARY_SHA256SUM = "978391a174e71cfef444ab9dc012f95d5d7eae0d682eaf1da2ea18f793452031"

WORKLOAD_BINARY_DIR = "/opt/promtail"
WORKLOAD_BINARY_FILE_NAME = "promtail-linux-amd64"
WORKLOAD_BINARY_PATH = "{}/{}".format(WORKLOAD_BINARY_DIR, WORKLOAD_BINARY_FILE_NAME)
WORKLOAD_CONFIG_DIR = "/etc/promtail"
WORKLOAD_CONFIG_FILE_NAME = "promtail_config.yaml"
WORKLOAD_CONFIG_PATH = "{}/{}".format(WORKLOAD_CONFIG_DIR, WORKLOAD_CONFIG_FILE_NAME)
WORKLOAD_POSITIONS_PATH = "{}/positions.yaml".format(WORKLOAD_BINARY_DIR)
WORKLOAD_SERVICE_NAME = "promtail"

DEFAULT_RELATION_NAME = "log_proxy"
HTTP_LISTEN_PORT = 9080
GRPC_LISTEN_PORT = 9095


class PromtailDigestError(Exception):
    """Raised if there is an error with Promtail binary file."""


class RelationManagerBase(Object):
    """Base class that represents relation ends ("provides" and "requires").

    :class:`RelationManagerBase` is used to create a relation manager. This is done by inheriting
    from :class:`RelationManagerBase` and customising the sub class as required.

    Attributes:
        name (str): consumer's relation name
    """

    def __init__(self, charm: CharmBase, relation_name=DEFAULT_RELATION_NAME):
        super().__init__(charm, relation_name)
        self._relation_name = relation_name


class LogProxyConsumer(RelationManagerBase):
    """LogProxyConsumer class."""

    _stored = StoredState()

    def __init__(
        self,
        charm,
        container_name: Optional[str],
        relation_name: str = DEFAULT_RELATION_NAME,
        log_type: str = "files",
        log_files: list = None,
        syslog_port: int = 1514,
    ):
        super().__init__(charm, relation_name)
        self._stored.set_default(grafana_agents="{}")
        self._charm = charm
        self._relation_name = relation_name
        self._container_name = container_name
        self._container = self._get_container(container_name)
        self._log_files = log_files or []
        self._syslog_port = syslog_port
        if log_type == "syslog":
            self._is_syslog = True
        elif log_type == "files":
            self._is_syslog = False
        else:
            raise Exception('log_type should be "syslog" or "files"')
        self.framework.observe(
            self._charm.on.log_proxy_relation_created, self._on_log_proxy_relation_created
        )
        self.framework.observe(
            self._charm.on.log_proxy_relation_changed, self._on_log_proxy_relation_changed
        )
        self.framework.observe(
            self._charm.on.log_proxy_relation_departed, self._on_log_proxy_relation_departed
        )

    def _on_log_proxy_relation_created(self, event):
        """Event handler for the `log_proxy_relation_created`."""
        self._create_directories()
        self._container.push(
            WORKLOAD_CONFIG_PATH, yaml.safe_dump(self._initial_config), make_dirs=True
        )

    def _on_log_proxy_relation_changed(self, event):
        """Event handler for the `log_proxy_relation_changed`.

        Args:
            event: The event object `RelationChangedEvent`.
        """
        if event.relation.data[event.unit].get("data", None):
            try:
                self._obtain_promtail(event)
                self._update_config(event)
                self._update_agents_list(event)
                self._add_pebble_layer()
                self._container.restart(self._container_name)
                self._container.restart(WORKLOAD_SERVICE_NAME)
            except HTTPError as e:
                msg = "Promtail binary couldn't be download - {}".format(str(e))
                logger.warning(msg)
                raise PromtailDigestError(msg)

    def _on_log_proxy_relation_departed(self, event):
        """Event handler for the `log_proxy_relation_departed`.

        Args:
            event: The event object `RelationDepartedEvent`.
        """
        self._update_config(event)
        self._update_agents_list(event)

        if len(self._current_config["clients"]) == 0:
            self._container.stop(WORKLOAD_SERVICE_NAME)
        else:
            self._container.restart(WORKLOAD_SERVICE_NAME)

    def _get_container(self, container_name):
        """Gets a single container by name or using the only container running in the Pod.

        If there is more than one container in the Pod a `PromtailDigestError` is raised.

        Args:
            container_name: The container name.

        Returns:
            container: a `ops.model.Container` object representing the container.

        Raises:
            PromtailDigestError if no `container_name` is passed and there is more than one
                container in the Pod.
        """
        if container_name is not None:
            try:
                return self._charm.unit.get_container(container_name)
            except ModelError as e:
                msg = str(e)
                logger.warning(msg)
                raise PromtailDigestError(msg)
        else:
            containers = dict(self._charm.model.unit.containers)

            if len(containers) == 1:
                return self._charm.unit.get_container([*containers].pop())

            msg = (
                "No 'container_name' parameter has been specified; since this charmed operator"
                " is not running exactly one container, it must be specified which container"
                " to get logs from."
            )
            raise PromtailDigestError(msg)

    def _add_pebble_layer(self):
        """Adds Pebble layer that manages Promtail service in Workload container."""
        pebble_layer = {
            "summary": "promtail layer",
            "description": "pebble config layer for promtail",
            "services": {
                WORKLOAD_SERVICE_NAME: {
                    "override": "replace",
                    "summary": WORKLOAD_SERVICE_NAME,
                    "command": "{} {}".format(WORKLOAD_BINARY_PATH, self._cli_args),
                    "startup": "enabled",
                }
            },
        }
        self._container.add_layer(self._container_name, pebble_layer, combine=True)

    def _create_directories(self) -> None:
        """Creates the directories for Promtail binary and config file."""
        self._container.make_dir(path=WORKLOAD_BINARY_DIR, make_parents=True)
        self._container.make_dir(path=WORKLOAD_CONFIG_DIR, make_parents=True)

    def _obtain_promtail(self, event) -> None:
        if self._is_promtail_binary_in_workload():
            return

        if self._download_promtail(event):
            with open(BINARY_PATH, "rb") as f:
                self._container.push(WORKLOAD_BINARY_PATH, f, permissions=0o755, make_dirs=True)

    def _is_promtail_binary_in_workload(self) -> bool:
        """Check if Promtail binary is already stored in workload container.

        Returns:
            a boolean representing whether Promtail is present or not.
        """
        cont = self._container.list_files(WORKLOAD_BINARY_DIR, pattern=WORKLOAD_BINARY_FILE_NAME)
        return True if len(cont) == 1 else False

    def _download_promtail(self, event) -> bool:
        """Downloads Promtail zip file and checks if its sha256 is correct.

        Returns:
            True if zip file was downloaded, else returns false.

        Raises:
            Raises PromtailDigestError if its sha256 is wrong.
        """
        url = json.loads(event.relation.data[event.unit].get("data"))["promtail_binary_zip_url"]

        with urlopen(url) as r:
            file_bytes = r.read()
            result = sha256(file_bytes).hexdigest()

            if result != BINARY_SHA256SUM:
                logger.error(
                    "promtail binary mismatch, expected:'{}' but got '{}'",
                    BINARY_SHA256SUM,
                    result,
                )
                raise PromtailDigestError("Digest mismatch for promtail binary")

            ZipFile(BytesIO(file_bytes)).extractall(BINARY_DIR)

        return True if Path(BINARY_PATH).is_file() else False

    def _update_agents_list(self, event):
        """Updates the active Grafana agents list.

        Args:
            event: The event object `RelationChangedEvent` or `RelationDepartedEvent`
        """
        grafana_agents = json.loads(self._stored.grafana_agents)

        if isinstance(event, RelationChangedEvent):
            agent_url = json.loads(event.relation.data[event.unit].get("data"))["loki_push_api"]
            grafana_agents[str(event.unit)] = agent_url
            self._stored.grafana_agents = json.dumps(grafana_agents)
        elif isinstance(event, RelationDepartedEvent):
            agent_url = grafana_agents.pop(str(event.unit))
            self._stored.grafana_agents = json.dumps(grafana_agents)

    def _update_config(self, event):
        """Updates the config file for Promtail and upload it to the side-car container.

        Args:
            event: `RelationChangedEvent` or `RelationDepartedEvent`
        """
        config = self._build_config_file(event)
        self._container.push(WORKLOAD_CONFIG_PATH, config, make_dirs=True)

    @property
    def _cli_args(self) -> str:
        """Return the cli arguments to pass to promtail.

        Returns:
            The arguments as a string
        """
        return "-config.file={}".format(WORKLOAD_CONFIG_PATH)

    @property
    def _current_config(self) -> dict:
        """Property that returns the current Promtail configuration.

        Returns:
            A dict containing Promtail configuration.
        """
        raw_current = self._container.pull(WORKLOAD_CONFIG_PATH).read()
        current_config = yaml.safe_load(raw_current)
        return current_config

    def _build_config_file(self, event) -> str:
        """Generates config file str based on the event received.

        Args:
            event: `RelationChangedEvent` or `RelationDepartedEvent`

        Returns:
            A yaml string with Promtail config.
        """
        config = {}
        current_config = self._current_config.copy()

        if isinstance(event, RelationChangedEvent):
            agent_url = json.loads(event.relation.data[event.unit].get("data"))["loki_push_api"]
            config = self._add_client(current_config, agent_url)
        elif isinstance(event, RelationDepartedEvent):
            agent_url = json.loads(self._stored.grafana_agents)[str(event.unit)]
            config = self._remove_client(current_config, agent_url)

        return yaml.safe_dump(config)

    @property
    def _initial_config(self) -> dict:
        """Generates an initial config for Promtail.

        This config it's going to be completed with the `client` section
        once a relation between Grafana Agent charm and a workload charm is established.
        """
        config = {}
        config.update(self._server_config())
        config.update(self._positions())
        config.update(self._scrape_configs())
        return config

    def _add_client(self, current_config: dict, agent_url: str) -> dict:
        """Updates Promtail's current configuration by adding a Grafana Agent URL.

        Args:
            current_config: A dictionary containing Promtail current configuration.
            agent_url: A string with Grafana Agent URL.

        Returns:
            Updated Promtail configuration.
        """
        if "clients" in current_config:
            current_config["clients"].append({"url": agent_url})
        else:
            current_config["clients"] = [{"url": agent_url}]

        return current_config

    def _remove_client(self, current_config, agent_url) -> dict:
        """Updates Promtail's current configuration by removing a Grafana Agent URL.

        Args:
            current_config: A dictionary containing Promtail current configuration.
            agent_url: A string with Grafana Agent URL.

        Returns:
            Updated Promtail configuration.
        """
        clients = current_config.get("clients", None)

        if clients:
            clients = [c for c in clients if c != {"url": agent_url}]
            current_config["clients"] = clients
            return current_config

        return current_config

    def _server_config(self) -> dict:
        """Generates the server section of the Promtail config file.

        Returns:
            A dict representing the `server` section.
        """
        return {
            "server": {
                "http_listen_port": HTTP_LISTEN_PORT,
                "grpc_listen_port": GRPC_LISTEN_PORT,
            }
        }

    def _positions(self) -> dict:
        """Generates the positions section of the Promtail config file.

        Returns:
            A dict representing the `positions` section.
        """
        return {"positions": {"filename": WORKLOAD_POSITIONS_PATH}}

    def _scrape_configs(self) -> dict:
        """Generates the scrape_configs section of the Promtail config file.

        Returns:
            A dict representing the `scrape_configs` section.
        """
        # TODO: use the JujuTopology object
        labels = {
            "job": "juju_{}_{}_{}".format(
                self._charm.model.name,
                self._charm.model.uuid,
                self._charm.model.app.name,
            ),
            "__path__": "",
        }

        if self._is_syslog:
            scrape_config = {
                "job_name": "syslog",
                "syslog": {
                    "listen_address": "127.0.0.1:{}".format(self._syslog_port),
                    "label_structured_data": True,
                    "labels": labels,
                },
            }
        else:
            config = {
                "targets": ["localhost"],
                "labels": labels
            }
            scrape_config = {
                "job_name": "system",
                "static_configs": self._generate_static_configs(config),
            }

        return {"scrape_configs": [scrape_config]}

    def _generate_static_configs(self, config: dict) -> list:
        """Generates static_configs section.

        Returns:
            - a list of dictionaries representing static_configs section
        """
        static_configs = []

        for _file in self._log_files:
            conf = deepcopy(config)
            conf["labels"]["__path__"] = _file
            static_configs.append(conf)

        return static_configs

    @property
    def syslog_port(self):
        return self._syslog_port

    @property
    def rsyslog_config(self):
        return 'action(type="omfwd" protocol="tcp" target="127.0.0.1" port="{}" Template="RSYSLOG_SyslogProtocol23Format" TCP_Framing="octet-counted")'.format(self._syslog_port)


class LogProxyProvider(RelationManagerBase):
    """LogProxyProvider class."""

    def __init__(self, charm, relation_name: str = DEFAULT_RELATION_NAME):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self.framework.observe(
            self._charm.on.log_proxy_relation_changed, self._on_log_proxy_relation_changed
        )

    def _on_log_proxy_relation_changed(self, event):
        if event.relation.data[self._charm.unit].get("data") is None:
            data = {}
            data.update(json.loads(self._loki_push_api))
            data.update(json.loads(self._promtail_binary_url))
            event.relation.data[self._charm.unit].update({"data": json.dumps(data)})

    @property
    def _promtail_binary_url(self) -> str:
        """URL from which Promtail binary can be downloaded."""
        # FIXME: Use charmhub's URL
        return json.dumps({"promtail_binary_zip_url": PROMTAIL_BINARY_ZIP_URL})

    @property
    def _loki_push_api(self) -> str:
        """Fetch Loki push API URL.

        Returns:
            Loki push API URL as json string
        """
        loki_push_api = "http://{}:{}/loki/api/v1/push".format(
            self.unit_ip, self._charm._http_listen_port
        )
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP."""
        bind_address = self._charm.model.get_binding(self._relation_name).network.bind_address

        if bind_address:
            return str(bind_address)
        return ""
