#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

r"""## Overview.

This document explains how to use the two principal objects this library provides:

- `LokiPushApiProvider`: This object is meant to be used by any Charmed Operator that needs to
implement the provider side of the `loki_push_api` relation interface. For instance, a Loki charm.
The provider side of the relation represents the server side, to which logs are being pushed.

- `LokiPushApiConsumer`: This object is meant to be used by any Charmed Operator that needs to
send log to Loki by implementing the consumer side of the `loki_push_api` relation interface.
For instance, a Promtail or Grafana agent charm which needs to send logs to Loki.

- `LogProxyConsumer`: This object can be used by any Charmed Operator which needs to
send telemetry, such as logs, to Loki through a Log Proxy by implementing the consumer side of the
`loki_push_api` relation interface.

Filtering logs in Loki is largely performed on the basis of labels. In the Juju ecosystem, Juju
topology labels are used to uniquely identify the workload which generates telemetry like logs.

In order to be able to control the labels on the logs pushed this object adds a Pebble layer
that runs Promtail in the workload container, injecting Juju topology labels into the
logs on the fly.

## LokiPushApiProvider Library Usage

This object may be used by any Charmed Operator which implements the `loki_push_api` interface.
For instance, Loki or Grafana Agent.

For this purposes a charm needs to instantiate the `LokiPushApiProvider` object with one mandatory
and three optional arguments.

- `charm`: A reference to the parent (Loki) charm.

- `relation_name`: The name of the relation that the charm uses to interact
  with its clients, which implement `LokiPushApiConsumer` or `LogProxyConsumer`.

  If provided, this relation name must match a provided relation in metadata.yaml with the
  `loki_push_api` interface.

  Typically `LokiPushApiConsumer` use "logging" as a relation_name and `LogProxyConsumer` use
  "log_proxy".

  The default value of this arguments is "logging".

  An example of this in a `metadata.yaml` file should have the following section:

  ```yaml
  provides:
    logging:
      interface: loki_push_api
  ```

  For example, a Loki charm may instantiate the `LokiPushApiProvider` in its constructor as
  follows:

      from charms.loki_k8s.v0.loki_push_api import LokiPushApiProvider
      from loki_server import LokiServer
      ...

      class LokiOperatorCharm(CharmBase):
          ...

          def __init__(self, *args):
              super().__init__(*args)
              ...
              self._provide_loki()
              ...

          def _provide_loki(self):
              try:
                  version = self._loki_server.version
                  self.loki_provider = LokiPushApiProvider(self)
                  logger.debug("Loki Provider is available. Loki version: %s", version)
              except LokiServerNotReadyError as e:
                  self.unit.status = MaintenanceStatus(str(e))
              except LokiServerError as e:
                  self.unit.status = BlockedStatus(str(e))

  - `port`: Loki Push Api endpoint port. Default value: 3100.
  - `rules_dir`: Directory to store alert rules. Default value: "/loki/rules".


The `LokiPushApiProvider` object has several responsibilities:

1. Set the URL of the Loki Push API in the relation application data bag; the URL
   must be unique to all instances (e.g. using a load balancer).

2. Set the Promtail binary URL (`promtail_binary_zip_url`) so clients that use
   `LogProxyConsumer` object can downloaded and configure it.

3. Process the metadata of the consumer application, provided via the
   "metadata" field of the consumer data bag, which are used to annotate the
   alert rules (see next point). An example for "metadata" is the following:

    {'model': 'loki',
     'model_uuid': '0b7d1071-ded2-4bf5-80a3-10a81aeb1386',
     'application': 'promtail-k8s'
    }

4. Process alert rules set into the relation by the `LokiPushApiConsumer`
   objects, e.g.:

    '{
         "groups": [{
             "name": "loki_0b7d1071-ded2-4bf5-80a3-10a81aeb1386_promtail-k8s_alerts",
             "rules": [{
                 "alert": "HighPercentageError",
                 "expr": "sum(rate({app=\\"foo\\", env=\\"production\\"} |= \\"error\\" [5m]))
                          by (job) \\n  /\\nsum(rate({app=\\"foo\\", env=\\"production\\"}[5m]))
                          by (job)\\n  > 0.05
                          \\n", "for": "10m",
                 "labels": {
                     "severity": "page",
                     "juju_model": "loki",
                     "juju_model_uuid": "0b7d1071-ded2-4bf5-80a3-10a81aeb1386",
                     "juju_application": "promtail-k8s"
                },
                "annotations": {
                    "summary": "High request latency"
               }
             }]
         }]
     }'


Once these alert rules are sent over relation data, the `LokiPushApiProvider` object
stores these files in the directory `/loki/rules` inside the Loki charm container.

## LokiPushApiConsumer Library Usage

This Loki charm interacts with its clients using the Loki charm library. Charms
seeking to send log to Loki, must do so using the `LokiPushApiConsumer` object from
this charm library.

For the simplest use cases, using the `LokiPushApiConsumer` object only requires
instantiating it, typically in the constructor of your charm (the one which
sends logs).

```python
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer

class LokiClientCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        ...
        self._loki_consumer = LokiPushApiConsumer(self)
```

The `LokiPushApiConsumer` constructor requires two things:

- A reference to the parent (LokiClientCharm) charm.

- Optionally, the name of the relation that the Loki charm uses to interact
  with its clients. If provided, this relation name must match a required
  relation in metadata.yaml with the `loki_push_api` interface.

  This argument is not required if your metadata.yaml has precisely one
  required relation in metadata.yaml with the `loki_push_api` interface, as the
  lib will automatically resolve the relation name inspecting the using the
  meta information of the charm

Any time the relation between a Loki provider charm and a Loki consumer charm is
established, a `LokiPushApiEndpointJoined` event is fired. In the consumer side
is it possible to observe this event with:

```python

self.framework.observe(
    self._loki_consumer.on.loki_push_api_endpoint_joined,
    self._on_loki_push_api_endpoint_joined,
)
```

Any time there are departures in relations between the consumer charm and Loki
the consumer charm is informed, through a `LokiPushApiEndpointDeparted` event, for instance:

```python
self.framework.observe(
    self._loki_consumer.on.loki_push_api_endpoint_departed,
    self._on_loki_push_api_endpoint_departed,
)
```

The consumer charm can then choose to update its configuration in both situations.

## LogProxyConsumer Library Usage

Let's say that we have a workload charm that produces logs and we need to send those logs to a
workload implementing the `loki_push_api` interface, such as `Loki` or `Grafana Agent`.

Adopting this object in a Charmed Operator consist of two steps:

1. Use the `LogProxyConsumer` class by instanting it in the `__init__` method of the charmed
   operator. There are two ways to get logs in to promtail. You can give it a list of files to read
   or you can write to it using the syslog protocol.

   For example:

   ```python
   from charms.loki_k8s.v0.log_proxy import LogProxyConsumer

   ...

       def __init__(self, *args):
           ...
           self._log_proxy = LogProxyConsumer(
               charm=self, log_files=LOG_FILES, container_name=PEER, enable_syslog=True
           )

           self.framework.observe(
               self._loki_consumer.on.promtail_digest_error,
               self._promtail_error,
           )

           def _promtail_error(self, event):
               logger.error(msg)
               self.unit.status = BlockedStatus(event.message)
   ```

   Any time the relation between a provider charm and a LogProxy consumer charm is
   established, a `LogProxyEndpointJoined` event is fired. In the consumer side is it
   possible to observe this event with:

   ```python

   self.framework.observe(
       self._log_proxy.on.log_proxy_endpoint_joined,
       self._on_log_proxy_endpoint_joined,
   )
   ```

   Any time there are departures in relations between the consumer charm and the provider
   the consumer charm is informed, through a `LogProxyEndpointDeparted` event, for instance:

   ```python
   self.framework.observe(
       self._log_proxy.on.log_proxy_endpoint_departed,
       self._on_log_proxy_endpoint_departed,
   )
   ```

   The consumer charm can then choose to update its configuration in both situations.

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
      If in the Pod there is only one container, this argument can be omitted.

   - You can configure your syslog software using `localhost` as the address and the method
     `LogProxyConsumer.syslog_port` to get the port, or, alternatively, if you are using rsyslog
     you may use the method `LogProxyConsumer.rsyslog_config()`.

2. Modify the `metadata.yaml` file to add:

   - The `log_proxy` relation in the `requires` section:
     ```yaml
     requires:
       log_proxy:
         interface: loki_push_api
         optional: true
     ```

Once the library is implemented in a Charmed Operator and a relation is established with
the charm that implements the `loki_push_api` interface, the library will inject a
Pebble layer that runs Promtail in the workload container to send logs.

By default, the promtail binary injected into the container will be downloaded from the internet.
If, for any reason, the container has limited network access, you may allow charm administrators
to provide their own promtail binary at runtime by adding the following snippet to your charm
metadata:

```yaml
resources:
  promtail-bin:
      type: file
      description: Promtail binary for logging
      filename: promtail-linux-amd64
```

Which would then allow operators to deploy the charm this way:

```
juju deploy \
    ./your_charm.charm \
    --resource promtail-bin=/tmp/promtail-linux-amd64
```

The object can emit a `PromtailDigestError` event:

- Promtail binary cannot be downloaded.
- The sha256 sum mismatch for promtail binary.

The object can raise a `ContainerNotFoundError` event:

- No `container_name` parameter has been specified and the Pod has more than 1 container.

These can be monitored via the PromtailDigestError events via:

```python
   self.framework.observe(
       self._loki_consumer.on.promtail_digest_error,
       self._promtail_error,
   )

   def _promtail_error(self, event):
       logger.error(msg)
       self.unit.status = BlockedStatus(event.message)
    )
```

## Alerting Rules

This charm library also supports gathering alerting rules from all related Loki client
charms and enabling corresponding alerts within the Loki charm. Alert rules are
automatically gathered by `LokiPushApiConsumer` object from a directory conventionally
named `loki_alert_rules`.

This directory must reside at the top level in the `src` folder of the
consumer charm. Each file in this directory is assumed to be a single alert rule
in YAML format. The file name must have the `.rule` extension.
The format of this alert rule conforms to the
[Loki docs](https://grafana.com/docs/loki/latest/rules/#alerting-rules).

An example of the contents of one such file is shown below.

```yaml
alert: HighPercentageError
expr: |
  sum(rate({%%juju_topology%%} |= "error" [5m])) by (job)
    /
  sum(rate({%%juju_topology%%}[5m])) by (job)
    > 0.05
for: 10m
labels:
    severity: page
annotations:
    summary: High request latency

```

It is **critical** to use the `%%juju_topology%%` filter in the expression for the alert
rule shown above. This filter is a stub that is automatically replaced by the
`LokiPushApiConsumer` following Loki Client's Juju topology (application, model and its
UUID). Such a topology filter is essential to ensure that alert rules submitted by one
provider charm generates alerts only for that same charm.

The Loki charm may be related to multiple Loki client charms. Without this, filter
rules submitted by one provider charm will also result in corresponding alerts for other
provider charms. Hence every alert rule expression must include such a topology filter stub.

Gathering alert rules and generating rule files within the Loki charm is easily done using
the `alerts()` method of `LokiPushApiProvider`. Alerts generated by Loki will automatically
include Juju topology labels in the alerts. These labels indicate the source of the alert.

The following labels are automatically added to every alert

- `juju_model`
- `juju_model_uuid`
- `juju_application`


Whether alert rules files does not contain the keys `alert` or `expr` or there is no alert
rules file in `alert_rules_path` a `loki_push_api_alert_rules_error` event is emitted.

To handle these situations the event must be observed in the `LokiClientCharm` charm.py file:

```python
class LokiClientCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        ...
        self._loki_consumer = LokiPushApiConsumer(self)

        self.framework.observe(
            self._loki_consumer.on.loki_push_api_alert_rules_error,
            self._alert_rules_error
        )

    def _alert_rules_error(self, event):
        self.unit.status = BlockedStatus(event.message)
```

## Relation Data

The Loki charm uses both application and unit relation data to obtain information regarding
Loki Push API and alert rules.

Units of consumer charm send their alert rules over app relation data using the `alert_rules`
key.
"""

import json
import logging
import os
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

import yaml
from ops.charm import (
    CharmBase,
    HookEvent,
    RelationCreatedEvent,
    RelationDepartedEvent,
    RelationEvent,
    RelationRole,
    WorkloadEvent,
)
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from ops.model import Container, ModelError, Relation
from ops.pebble import APIError, PathError, ProtocolError

# The unique Charmhub library identifier, never change it
LIBID = "bf76f23cdd03464b877c52bd1d2f563e"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 9

logger = logging.getLogger(__name__)

RELATION_INTERFACE_NAME = "loki_push_api"
DEFAULT_RELATION_NAME = "logging"
DEFAULT_ALERT_RULES_RELATIVE_PATH = "./src/loki_alert_rules"
DEFAULT_LOG_PROXY_RELATION_NAME = "log-proxy"

PROMTAIL_BINARY_ZIP_URL = (
    "https://github.com/grafana/loki/releases/download/v2.4.1/promtail-linux-amd64.zip"
)


# Paths in `charm` container
BINARY_DIR = "/tmp"
BINARY_ZIP_FILE_NAME = "promtail-linux-amd64.zip"
BINARY_ZIP_PATH = "{}/{}".format(BINARY_DIR, BINARY_ZIP_FILE_NAME)
BINARY_FILE_NAME = "promtail-linux-amd64"
BINARY_PATH = "{}/{}".format(BINARY_DIR, BINARY_FILE_NAME)
BINARY_ZIP_SHA256SUM = "978391a174e71cfef444ab9dc012f95d5d7eae0d682eaf1da2ea18f793452031"
BINARY_SHA256SUM = "00ed6a4b899698abc97d471c483a6a7e7c95e761714f872eb8d6ffd45f3d32e6"

# Paths in `workload` container
WORKLOAD_BINARY_DIR = "/opt/promtail"
WORKLOAD_BINARY_FILE_NAME = "promtail-linux-amd64"
WORKLOAD_BINARY_PATH = "{}/{}".format(WORKLOAD_BINARY_DIR, WORKLOAD_BINARY_FILE_NAME)
WORKLOAD_CONFIG_DIR = "/etc/promtail"
WORKLOAD_CONFIG_FILE_NAME = "promtail_config.yaml"
WORKLOAD_CONFIG_PATH = "{}/{}".format(WORKLOAD_CONFIG_DIR, WORKLOAD_CONFIG_FILE_NAME)
WORKLOAD_POSITIONS_PATH = "{}/positions.yaml".format(WORKLOAD_BINARY_DIR)
WORKLOAD_SERVICE_NAME = "promtail"

HTTP_LISTEN_PORT = 9080
GRPC_LISTEN_PORT = 9095


class RelationNotFoundError(ValueError):
    """Raised if there is no relation with the given name."""

    def __init__(self, relation_name: str):
        self.relation_name = relation_name
        self.message = "No relation named '{}' found".format(relation_name)

        super().__init__(self.message)


class RelationInterfaceMismatchError(Exception):
    """Raised if the relation with the given name has a different interface."""

    def __init__(
        self,
        relation_name: str,
        expected_relation_interface: str,
        actual_relation_interface: str,
    ):
        self.relation_name = relation_name
        self.expected_relation_interface = expected_relation_interface
        self.actual_relation_interface = actual_relation_interface
        self.message = (
            "The '{}' relation has '{}' as interface rather than the expected '{}'".format(
                relation_name, actual_relation_interface, expected_relation_interface
            )
        )
        super().__init__(self.message)


class RelationRoleMismatchError(Exception):
    """Raised if the relation with the given name has a different direction."""

    def __init__(
        self,
        relation_name: str,
        expected_relation_role: RelationRole,
        actual_relation_role: RelationRole,
    ):
        self.relation_name = relation_name
        self.expected_relation_interface = expected_relation_role
        self.actual_relation_role = actual_relation_role
        self.message = "The '{}' relation has role '{}' rather than the expected '{}'".format(
            relation_name, repr(actual_relation_role), repr(expected_relation_role)
        )
        super().__init__(self.message)


def _validate_relation_by_interface_and_direction(
    charm: CharmBase,
    relation_name: str,
    expected_relation_interface: str,
    expected_relation_role: RelationRole,
):
    """Verifies that a relation has the necessary characteristics.

    Verifies that the `relation_name` provided: (1) exists in metadata.yaml,
    (2) declares as interface the interface name passed as `relation_interface`
    and (3) has the right "direction", i.e., it is a relation that `charm`
    provides or requires.

    Args:
        charm: a `CharmBase` object to scan for the matching relation.
        relation_name: the name of the relation to be verified.
        expected_relation_interface: the interface name to be matched by the
            relation named `relation_name`.
        expected_relation_role: whether the `relation_name` must be either
            provided or required by `charm`.

    Raises:
        RelationNotFoundError: If there is no relation in the charm's metadata.yaml
            with the same name as provided via `relation_name` argument.
        RelationInterfaceMismatchError: The relation with the same name as provided
            via `relation_name` argument does not have the same relation interface
            as specified via the `expected_relation_interface` argument.
        RelationRoleMismatchError: If the relation with the same name as provided
            via `relation_name` argument does not have the same role as specified
            via the `expected_relation_role` argument.
    """
    if relation_name not in charm.meta.relations:
        raise RelationNotFoundError(relation_name)

    relation = charm.meta.relations[relation_name]

    actual_relation_interface = relation.interface_name
    if actual_relation_interface != expected_relation_interface:
        raise RelationInterfaceMismatchError(
            relation_name, expected_relation_interface, actual_relation_interface
        )

    if expected_relation_role == RelationRole.provides:
        if relation_name not in charm.meta.provides:
            raise RelationRoleMismatchError(
                relation_name, RelationRole.provides, RelationRole.requires
            )
    elif expected_relation_role == RelationRole.requires:
        if relation_name not in charm.meta.requires:
            raise RelationRoleMismatchError(
                relation_name, RelationRole.requires, RelationRole.provides
            )
    else:
        raise Exception("Unexpected RelationDirection: {}".format(expected_relation_role))


class JujuTopology:
    """Class for storing and formatting juju topology information."""

    STUB = "%%juju_topology%%"

    def __new__(cls, *args, **kwargs):
        """Reject instantiation of a base JujuTopology class. Children only."""
        if cls is JujuTopology:
            raise TypeError("only children of '{}' may be instantiated".format(cls.__name__))
        return object.__new__(cls)

    def __init__(
        self,
        model: str,
        model_uuid: str,
        application: str,
        unit: Optional[str] = "",
        charm_name: Optional[str] = "",
    ):
        """Build a JujuTopology object.

        A `JujuTopology` object is used for storing and transforming
        Juju Topology information. This information is used to
        annotate Prometheus scrape jobs and alert rules. Such
        annotation when applied to scrape jobs helps in identifying
        the source of the scrapped metrics. On the other hand when
        applied to alert rules topology information ensures that
        evaluation of alert expressions is restricted to the source
        (charm) from which the alert rules were obtained.

        Args:
            model: a string name of the Juju model
            model_uuid: a globally unique string identifier for the Juju model
            application: an application name as a string
            unit: a unit name as a string
            charm_name: name of charm as a string
        """
        self.model = model
        self.model_uuid = model_uuid
        self.application = application
        self.charm_name = charm_name
        self.unit = unit

    @classmethod
    def from_charm(cls, charm) -> "JujuTopology":
        """Factory method for creating `JujuTopology` children from a given charm.

        Args:
            charm: a `CharmBase` object for which the `JujuTopology` has to be constructed

        Returns:
            a `JujuTopology` object.
        """
        return cls(
            model=charm.model.name,
            model_uuid=charm.model.uuid,
            application=charm.model.app.name,
            unit=charm.model.unit.name,
            charm_name=charm.meta.name,
        )

    @classmethod
    def from_relation_data(cls, data: dict) -> "JujuTopology":
        """Factory method for creating `JujuTopology` children from a dictionary.

        Args:
            data: a dictionary with four keys providing topology information. The keys are
                - "model"
                - "model_uuid"
                - "application"
                - "unit"
                - "charm_name"
                `unit` and `charm_name` may be empty, but will result in more limited
                labels. However, this allows us to support payload-only charms.

        Returns:
            a `JujuTopology` object.
        """
        return cls(
            model=data["model"],
            model_uuid=data["model_uuid"],
            application=data["application"],
            unit=data.get("unit", ""),
            charm_name=data.get("charm_name", ""),
        )

    @property
    def identifier(self) -> str:
        """Format the topology information into a terse string."""
        # This is odd, but may have `None` as a model key
        return "_".join([str(val) for val in self.as_dict().values()]).replace("/", "_")

    @property
    def promql_labels(self) -> str:
        """Format the topology information into a verbose string."""
        return ", ".join(
            [
                'juju_{}="{}"'.format(key, value)
                for key, value in self.as_dict(rename_keys={"charm_name": "charm"}).items()
            ]
        )

    def as_dict(self, rename_keys: Optional[Dict[str, str]] = None) -> OrderedDict:
        """Format the topology information into a dict.

        Use an OrderedDict so we can rely on the insertion order on Python 3.5 (and 3.6,
        which still does not guarantee it).

        Args:
            rename_keys: A dictionary mapping old key names to new key names, which will
                be substituted when invoked.
        """
        ret = OrderedDict(
            [
                ("model", self.model),
                ("model_uuid", self.model_uuid),
                ("application", self.application),
                ("unit", self.unit),
                ("charm_name", self.charm_name),
            ]
        )

        ret["unit"] or ret.pop("unit")
        ret["charm_name"] or ret.pop("charm_name")

        # If a key exists in `rename_keys`, replace the value
        if rename_keys:
            ret = OrderedDict(
                (rename_keys.get(k), v) if rename_keys.get(k) else (k, v) for k, v in ret.items()  # type: ignore
            )

        return ret

    def as_promql_label_dict(self) -> dict:
        """Format the topology information into a dict with keys having 'juju_' as prefix."""
        vals = {
            "juju_{}".format(key): val
            for key, val in self.as_dict(rename_keys={"charm_name": "charm"}).items()
        }

        return vals

    def render(self, template: str) -> str:
        """Render a juju-topology template string with topology info."""
        return template.replace(JujuTopology.STUB, self.promql_labels)


class AggregatorTopology(JujuTopology):
    """Class for initializing topology information for MetricsEndpointAggregator."""

    @classmethod
    def create(
        cls, model: str, model_uuid: str, application: str, unit: str
    ) -> "AggregatorTopology":
        """Factory method for creating the `AggregatorTopology` dataclass from a given charm.

        Args:
            model: a string representing the model
            model_uuid: the model UUID as a string
            application: the application name
            unit: the unit name

        Returns:
            a `AggregatorTopology` object.
        """
        return cls(
            model=model,
            model_uuid=model_uuid,
            application=application,
            unit=unit,
        )

    def as_promql_label_dict(self) -> dict:
        """Format the topology information into a dict with keys having 'juju_' as prefix."""
        vals = {"juju_{}".format(key): val for key, val in self.as_dict().items()}

        # FIXME: Why is this different? I have no idea. The uuid length should be the same
        vals["juju_model_uuid"] = vals["juju_model_uuid"][:7]

        return vals


class ProviderTopology(JujuTopology):
    """Class for initializing topology information for MetricsEndpointProvider."""

    @property
    def scrape_identifier(self) -> str:
        """Format the topology information into a scrape identifier."""
        # This is used only by Metrics[Consumer|Provider] and does not need a
        # unit name, so only check for the charm name
        return "juju_{}_prometheus_scrape".format(
            "_".join([self.model, self.model_uuid[:7], self.application, self.charm_name])  # type: ignore
        )


class InvalidAlertRulePathError(Exception):
    """Raised if the alert rules folder cannot be found or is otherwise invalid."""

    def __init__(
        self,
        alert_rules_absolute_path: Path,
        message: str,
    ):
        self.alert_rules_absolute_path = alert_rules_absolute_path
        self.message = message

        super().__init__(self.message)


def _is_official_alert_rule_format(rules_dict: dict) -> bool:
    """Are alert rules in the upstream format as supported by Loki.

    Alert rules in dictionary format are in "official" form if they
    contain a "groups" key, since this implies they contain a list of
    alert rule groups.

    Args:
        rules_dict: a set of alert rules in Python dictionary format

    Returns:
        True if alert rules are in official Loki file format.
    """
    return "groups" in rules_dict


def _is_single_alert_rule_format(rules_dict: dict) -> bool:
    """Are alert rules in single rule format.

    The Loki charm library supports reading of alert rules in a
    custom format that consists of a single alert rule per file. This
    does not conform to the official Loki alert rule file format
    which requires that each alert rules file consists of a list of
    alert rule groups and each group consists of a list of alert
    rules.

    Alert rules in dictionary form are considered to be in single rule
    format if in the least it contains two keys corresponding to the
    alert rule name and alert expression.

    Returns:
        True if alert rule is in single rule file format.
    """
    # one alert rule per file
    return set(rules_dict) >= {"alert", "expr"}


class AlertRules:
    """Utility class for amalgamating Loki alert rule files and injecting juju topology.

    An `AlertRules` object supports aggregating alert rules from files and directories in both
    official and single rule file formats using the `add_path()` method. All the alert rules
    read are annotated with Juju topology labels and amalgamated into a single data structure
    in the form of a Python dictionary using the `as_dict()` method. Such a dictionary can be
    easily dumped into JSON format and exchanged over relation data. The dictionary can also
    be dumped into YAML format and written directly into an alert rules file that is read by
    Loki. Note that multiple `AlertRules` objects must not be written into the same file,
    since Loki allows only a single list of alert rule groups per alert rules file.

    The official Loki format is a YAML file conforming to the Loki documentation
    (https://grafana.com/docs/loki/latest/api/#list-rule-groups).
    The custom single rule format is a subsection of the official YAML, having a single alert
    rule, effectively "one alert per file".
    """

    # This class uses the following terminology for the various parts of a rule file:
    # - alert rules file: the entire groups[] yaml, including the "groups:" key.
    # - alert groups (plural): the list of groups[] (a list, i.e. no "groups:" key) - it is a list
    #   of dictionaries that have the "name" and "rules" keys.
    # - alert group (singular): a single dictionary that has the "name" and "rules" keys.
    # - alert rules (plural): all the alerts in a given alert group - a list of dictionaries with
    #   the "alert" and "expr" keys.
    # - alert rule (singular): a single dictionary that has the "alert" and "expr" keys.

    def __init__(self, topology: Optional[JujuTopology] = None):
        """Build and alert rule object.

        Args:
            topology: a `JujuTopology` instance that is used to annotate all alert rules.
        """
        self.topology = topology
        self.alert_groups = []  # type: List[dict]

    def _from_file(self, root_path: Path, file_path: Path) -> List[dict]:
        """Read a rules file from path, injecting juju topology.

        Args:
            root_path: full path to the root rules folder (used only for generating group name)
            file_path: full path to a *.rule file.

        Returns:
            A list of dictionaries representing the rules file, if file is valid (the structure is
            formed by `yaml.safe_load` of the file); an empty list otherwise.
        """
        with file_path.open() as rf:
            # Load a list of rules from file then add labels and filters
            try:
                rule_file = yaml.safe_load(rf)

            except Exception as e:
                logger.error("Failed to read alert rules from %s: %s", file_path.name, e)
                return []

            if _is_official_alert_rule_format(rule_file):
                alert_groups = rule_file["groups"]
            elif _is_single_alert_rule_format(rule_file):
                # convert to list of alert groups
                # group name is made up from the file name
                alert_groups = [{"name": file_path.stem, "rules": [rule_file]}]
            else:
                # invalid/unsupported
                logger.error("Invalid rules file: %s", file_path.name)
                return []

            # update rules with additional metadata
            for alert_group in alert_groups:
                # update group name with topology and sub-path
                alert_group["name"] = self._group_name(
                    str(root_path),
                    str(file_path),
                    alert_group["name"],
                )

                # add "juju_" topology labels
                for alert_rule in alert_group["rules"]:
                    if "labels" not in alert_rule:
                        alert_rule["labels"] = {}

                    if self.topology:
                        alert_rule["labels"].update(self.topology.as_promql_label_dict())
                        # insert juju topology filters into a prometheus alert rule
                        alert_rule["expr"] = self.topology.render(alert_rule["expr"])

            return alert_groups

    def _group_name(self, root_path: str, file_path: str, group_name: str) -> str:
        """Generate group name from path and topology.

        The group name is made up of the relative path between the root dir_path, the file path,
        and topology identifier.

        Args:
            root_path: path to the root rules dir.
            file_path: path to rule file.
            group_name: original group name to keep as part of the new augmented group name

        Returns:
            New group name, augmented by juju topology and relative path.
        """
        rel_path = os.path.relpath(os.path.dirname(file_path), root_path)
        rel_path = "" if rel_path == "." else rel_path.replace(os.path.sep, "_")

        # Generate group name:
        #  - name, from juju topology
        #  - suffix, from the relative path of the rule file;
        group_name_parts = [self.topology.identifier] if self.topology else []
        group_name_parts.extend([rel_path, group_name, "alerts"])
        # filter to remove empty strings
        return "_".join(filter(None, group_name_parts))

    def _from_dir(self, dir_path: Path, recursive: bool) -> List[dict]:
        """Read all rule files in a directory.

        All rules from files for the same directory are loaded into a single
        group. The generated name of this group includes juju topology.
        By default, only the top directory is scanned; for nested scanning, pass `recursive=True`.

        Args:
            dir_path: directory containing *.rule files (alert rules without groups).
            recursive: flag indicating whether to scan for rule files recursively.

        Returns:
            a list of dictionaries representing prometheus alert rule groups, each dictionary
            representing an alert group (structure determined by `yaml.safe_load`).
        """
        alert_groups = []  # type: List[dict]

        # Gather all alerts into a list of groups
        paths = dir_path.glob("**/*.rule" if recursive else "*.rule")
        for file_path in filter(Path.is_file, paths):
            alert_groups_from_file = self._from_file(dir_path, file_path)
            if alert_groups_from_file:
                logger.debug("Reading alert rule from %s", file_path)
                alert_groups.extend(alert_groups_from_file)

        return alert_groups

    def add_path(self, path: str, *, recursive: bool = False):
        """Add rules from a dir path.

        All rules from files are aggregated into a data structure representing a single rule file.
        All group names are augmented with juju topology.

        Args:
            path: either a rules file or a dir of rules files.
            recursive: whether to read files recursively or not (no impact if `path` is a file).

        Raises:
            InvalidAlertRulePathError: if the provided path is invalid.
        """
        path = Path(path)  # type: Path
        if path.is_dir():
            self.alert_groups.extend(self._from_dir(path, recursive))
        elif path.is_file():
            self.alert_groups.extend(self._from_file(path.parent, path))
        else:
            logger.warning("path does not exist: %s", path)

    def as_dict(self) -> dict:
        """Return standard alert rules file in dict representation.

        Returns:
            a dictionary containing a single list of alert rule groups.
            The list of alert rule groups is provided as value of the
            "groups" dictionary key.
        """
        return {"groups": self.alert_groups} if self.alert_groups else {}


def _resolve_dir_against_charm_path(charm: CharmBase, *path_elements: str) -> str:
    """Resolve the provided path items against the directory of the main file.

    Look up the directory of the `main.py` file being executed. This is normally
    going to be the charm.py file of the charm including this library. Then, resolve
    the provided path elements and, if the result path exists and is a directory,
    return its absolute path; otherwise, raise en exception.

    Raises:
        InvalidAlertRulePathError, if the path does not exist or is not a directory.
    """
    charm_dir = Path(str(charm.charm_dir))
    if not charm_dir.exists() or not charm_dir.is_dir():
        # Operator Framework does not currently expose a robust
        # way to determine the top level charm source directory
        # that is consistent across deployed charms and unit tests
        # Hence for unit tests the current working directory is used
        # TODO: updated this logic when the following ticket is resolved
        # https://github.com/canonical/operator/issues/643
        charm_dir = Path(os.getcwd())

    alerts_dir_path = charm_dir.absolute().joinpath(*path_elements)

    if not alerts_dir_path.exists():
        raise InvalidAlertRulePathError(alerts_dir_path, "directory does not exist")
    if not alerts_dir_path.is_dir():
        raise InvalidAlertRulePathError(alerts_dir_path, "is not a directory")

    return str(alerts_dir_path)


class NoRelationWithInterfaceFoundError(Exception):
    """No relations with the given interface are found in the charm meta."""

    def __init__(self, charm: CharmBase, relation_interface: str = None):
        self.charm = charm
        self.relation_interface = relation_interface
        self.message = (
            "No relations with interface '{}' found in the meta of the '{}' charm".format(
                relation_interface, charm.meta.name
            )
        )

        super().__init__(self.message)


class MultipleRelationsWithInterfaceFoundError(Exception):
    """Multiple relations with the given interface are found in the charm meta."""

    def __init__(self, charm: CharmBase, relation_interface: str, relations: list):
        self.charm = charm
        self.relation_interface = relation_interface
        self.relations = relations
        self.message = (
            "Multiple relations with interface '{}' found in the meta of the '{}' charm.".format(
                relation_interface, charm.meta.name
            )
        )
        super().__init__(self.message)


class RelationManagerBase(Object):
    """Base class that represents relation ends ("provides" and "requires").

    :class:`RelationManagerBase` is used to create a relation manager. This is done by inheriting
    from :class:`RelationManagerBase` and customising the sub class as required.

    Attributes:
        name (str): consumer's relation name
    """

    def __init__(self, charm: CharmBase, relation_name):
        super().__init__(charm, relation_name)
        self.name = relation_name


class LokiPushApiEndpointDeparted(EventBase):
    """Event emitted when Loki departed."""


class LokiPushApiEndpointJoined(EventBase):
    """Event emitted when Loki joined."""


class LokiPushApiEvents(ObjectEvents):
    """Event descriptor for events raised by `LokiPushApiProvider`."""

    loki_push_api_endpoint_departed = EventSource(LokiPushApiEndpointDeparted)
    loki_push_api_endpoint_joined = EventSource(LokiPushApiEndpointJoined)


class LokiPushApiProvider(RelationManagerBase):
    """A LokiPushApiProvider class."""

    def __init__(
        self,
        charm,
        relation_name: str = DEFAULT_RELATION_NAME,
        *,
        port: int = 3100,
        rules_dir="/loki/rules",
    ):
        """A Loki service provider.

        Args:
            charm: a `CharmBase` instance that manages this
                instance of the Loki service.
            relation_name: an optional string name of the relation between `charm`
                and the Loki charmed service. The default is "logging".
                It is strongly advised not to change the default, so that people
                deploying your charm will have a consistent experience with all
                other charms that consume metrics endpoints.

            rules_dir: path in workload container where rule files are to be stored.

        Raises:
            RelationNotFoundError: If there is no relation in the charm's metadata.yaml
                with the same name as provided via `relation_name` argument.
            RelationInterfaceMismatchError: The relation with the same name as provided
                via `relation_name` argument does not have the `loki_push_api` relation
                interface.
            RelationRoleMismatchError: If the relation with the same name as provided
                via `relation_name` argument does not have the `RelationRole.requires`
                role.
        """
        _validate_relation_by_interface_and_direction(
            charm, relation_name, RELATION_INTERFACE_NAME, RelationRole.provides
        )
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self.port = port
        self.container = self._charm._container

        # If Loki is run in single-tenant mode, all the chunks are put in a folder named "fake"
        # https://grafana.com/docs/loki/latest/operations/storage/filesystem/
        # https://grafana.com/docs/loki/latest/rules/#ruler-storage
        tenant_id = "fake"
        self._rules_dir = os.path.join(rules_dir, tenant_id)
        # create tenant dir so that the /loki/api/v1/rules endpoint returns "no rule groups found"
        # instead of "unable to read rule dir /loki/rules/fake: no such file or directory"
        if self.container.can_connect():
            try:
                self.container.make_dir(self._rules_dir, make_parents=True)
            except (FileNotFoundError, ProtocolError, PathError):
                logger.debug("Could not create loki directory.")

        events = self._charm.on[relation_name]
        self.framework.observe(self._charm.on.upgrade_charm, self._on_logging_relation_changed)
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)
        self.framework.observe(events.relation_departed, self._on_logging_relation_departed)

    def _on_logging_relation_changed(self, event: HookEvent):
        """Handle changes in related consumers.

        Anytime there are changes in the relation between Loki
        and its consumers charms.

        Args:
            event: a `CharmEvent` in response to which the consumer
                charm must update its relation data.
        """
        if isinstance(event, RelationEvent):
            self._process_logging_relation_changed(event.relation)
        else:
            # Upgrade event or other charm-level event
            for relation in self._charm.model.relations[self._relation_name]:
                self._process_logging_relation_changed(relation)

    def _process_logging_relation_changed(self, relation: Relation):
        """Handle changes in related consumers.

        Anytime there are changes in relations between Loki
        and its consumers charms, Loki set the `loki_push_api`
        into the relation data.
        Besides Loki generates alert rules files based what
        consumer charms forwards,

        Args:
            relation: the `Relation` instance to update.
        """
        if self._charm.unit.is_leader():
            relation.data[self._charm.app].update(self._promtail_binary_url)
            logger.debug("Saved promtail binary url: %s", self._promtail_binary_url)
            relation.data[self._charm.app]["endpoints"] = json.dumps(self._endpoints())
            logger.debug("Saved endpoints in relation data")

        if relation.data.get(relation.app).get("alert_rules"):
            logger.debug("Saved alerts rules to disk")
            self._remove_alert_rules_files(self.container)
            self._generate_alert_rules_files(self.container)

    def _endpoints(self) -> List[dict]:
        """Return a list of Loki Push Api endpoints."""
        return [{"url": self._url(unit_number=i)} for i in range(self._charm.app.planned_units())]

    def _url(self, unit_number) -> str:
        """Get the url for a given unit."""
        return "http://{}-{}.{}-endpoints.{}.svc.cluster.local:{}/loki/api/v1/push".format(
            self._charm.app.name,
            unit_number,
            self._charm.app.name,
            self._charm.model.name,
            self.port,
        )

    def _on_logging_relation_departed(self, event: RelationDepartedEvent):
        """Removes alert rules files when consumer charms left the relation with Loki.

        Args:
            event: a `CharmEvent` in response to which the Loki
                charm must update its relation data.
        """
        if event.relation.data.get(event.relation.app):
            self._remove_alert_rules_files(self.container)

    @property
    def _promtail_binary_url(self) -> dict:
        """URL from which Promtail binary can be downloaded."""
        return {"promtail_binary_zip_url": PROMTAIL_BINARY_ZIP_URL}

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP."""
        bind_address = self._charm.model.get_binding(self._relation_name).network.bind_address

        if bind_address:
            return str(bind_address)
        return ""

    def _remove_alert_rules_files(self, container: Container) -> None:
        """Remove alert rules files from workload container.

        Args:
            container: Container which has alert rules files to be deleted
        """
        container.remove_path(self._rules_dir, recursive=True)
        logger.debug("Previous Alert rules files deleted")
        # Since container.remove_path deletes the directory itself with its files
        # we should create it again.
        os.makedirs(self._rules_dir, exist_ok=True)

    def _generate_alert_rules_files(self, container: Container) -> None:
        """Generate and upload alert rules files.

        Args:
            container: Container into which alert rules files are going to be uploaded
        """
        for identifier, alert_rules in self.alerts().items():
            filename = "{}_alert.rules".format(identifier)
            path = os.path.join(self._rules_dir, filename)
            rules = yaml.dump({"groups": alert_rules["groups"]})
            container.push(path, rules, make_dirs=True)
            logger.debug("Updated alert rules file %s", filename)

    def alerts(self) -> dict:
        """Fetch alerts for all relations.

        A Loki alert rules file consists of a list of "groups". Each
        group consists of a list of alerts (`rules`) that are sequentially
        executed. This method returns all the alert rules provided by each
        related metrics provider charm. These rules may be used to generate a
        separate alert rules file for each relation since the returned list
        of alert groups are indexed by relation ID. Also for each relation ID
        associated scrape metadata such as Juju model, UUID and application
        name are provided so the a unique name may be generated for the rules
        file. For each relation the structure of data returned is a dictionary
        with four keys

        - groups
        - model
        - model_uuid
        - application

        The value of the `groups` key is such that it may be used to generate
        a Loki alert rules file directly using `yaml.dump` but the
        `groups` key itself must be included as this is required by Loki,
        for example as in `yaml.dump({"groups": alerts["groups"]})`.

        Currently only accepts a list of rules and these
        rules are all placed into a single group, even though Loki itself
        allows for multiple groups within a single alert rules file.

        Returns:
            a dictionary of alert rule groups and associated scrape
            metadata indexed by relation ID.
        """
        alerts = {}  # type: Dict[str, dict] # mapping b/w juju identifiers and alert rule files
        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.units:
                continue

            alert_rules = json.loads(relation.data[relation.app].get("alert_rules", "{}"))
            if not alert_rules:
                continue

            try:
                # NOTE: this `metadata` key SHOULD NOT be changed to `scrape_metadata`
                # to align with Prometheus without careful consideration
                metadata = json.loads(relation.data[relation.app]["metadata"])
                identifier = ProviderTopology.from_relation_data(metadata).identifier
                alerts[identifier] = alert_rules
            except KeyError as e:
                logger.warning(
                    "Relation %s has no 'metadata': %s",
                    relation.id,
                    e,
                )

                if "groups" not in alert_rules:
                    logger.warning("No alert groups were found in relation data")
                    continue
                # Construct an ID based on what's in the alert rules
                for group in alert_rules["groups"]:
                    try:
                        labels = group["rules"][0]["labels"]
                        identifier = "{}_{}_{}".format(
                            labels["juju_model"],
                            labels["juju_model_uuid"],
                            labels["juju_application"],
                        )
                        alerts[identifier] = alert_rules
                    except KeyError:
                        logger.error("Alert rules were found but no usable labels were present")

        return alerts


class ConsumerBase(RelationManagerBase):
    """Consumer's base class."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        alert_rules_path: str = DEFAULT_ALERT_RULES_RELATIVE_PATH,
        recursive: bool = False,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self.topology = ProviderTopology.from_charm(charm)

        try:
            alert_rules_path = _resolve_dir_against_charm_path(charm, alert_rules_path)
        except InvalidAlertRulePathError as e:
            logger.warning(
                "Invalid Loki alert rules folder at %s: %s",
                e.alert_rules_absolute_path,
                e.message,
            )
        self._alert_rules_path = alert_rules_path

        self._recursive = recursive

    def _handle_alert_rules(self, relation):
        if not self._charm.unit.is_leader():
            return

        alert_rules = AlertRules(self.topology)
        alert_rules.add_path(self._alert_rules_path, recursive=self._recursive)
        alert_rules_as_dict = alert_rules.as_dict()

        # if alert_rules_error_message:
        #     self.on.loki_push_api_alert_rules_error.emit(alert_rules_error_message)

        relation.data[self._charm.app]["metadata"] = json.dumps(self.topology.as_dict())
        relation.data[self._charm.app]["alert_rules"] = json.dumps(
            alert_rules_as_dict,
            sort_keys=True,  # sort, to prevent unnecessary relation_changed events
        )


class LokiPushApiConsumer(ConsumerBase):
    """Loki Consumer class."""

    on = LokiPushApiEvents()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        alert_rules_path: str = DEFAULT_ALERT_RULES_RELATIVE_PATH,
        recursive: bool = True,
    ):
        """Construct a Loki charm client.

        The `LokiPushApiConsumer` object provides configurations to a Loki client charm.
        A charm instantiating this object needs Loki information, for instance the
        Loki API endpoint to push logs.
        The `LokiPushApiConsumer` can be instantiated as follows:

            self._loki_consumer = LokiPushApiConsumer(self)

        Args:
            charm: a `CharmBase` object that manages this `LokiPushApiConsumer` object.
                Typically this is `self` in the instantiating class.
            relation_name: the string name of the relation interface to look up.
                If `charm` has exactly one relation with this interface, the relation's
                name is returned. If none or multiple relations with the provided interface
                are found, this method will raise either an exception of type
                NoRelationWithInterfaceFoundError or MultipleRelationsWithInterfaceFoundError,
                respectively.
            alert_rules_path: a string indicating a path where alert rules can be found
            recursive: Whether or not to scan for rule files recursively.

        Raises:
            RelationNotFoundError: If there is no relation in the charm's metadata.yaml
                with the same name as provided via `relation_name` argument.
            RelationInterfaceMismatchError: The relation with the same name as provided
                via `relation_name` argument does not have the `loki_push_api` relation
                interface.
            RelationRoleMismatchError: If the relation with the same name as provided
                via `relation_name` argument does not have the `RelationRole.provides`
                role.

        Emits:
            loki_push_api_endpoint_joined: This event is emitted when the relation between the
                Charmed Operator that instantiates `LokiPushApiProvider` (Loki charm for instance)
                and the Charmed Operator that instantiates `LokiPushApiConsumer` is established.
            loki_push_api_endpoint_departed: This event is emitted when the relation between the
                Charmed Operator that implements `LokiPushApiProvider` (Loki charm for instance)
                and the Charmed Operator that implements `LokiPushApiConsumer` is removed.
            loki_push_api_alert_rules_error: This event is emitted when an invalid alert rules
                file is encountered or if `alert_rules_path` is empty.
        """
        _validate_relation_by_interface_and_direction(
            charm, relation_name, RELATION_INTERFACE_NAME, RelationRole.requires
        )
        super().__init__(charm, relation_name, alert_rules_path, recursive)
        events = self._charm.on[relation_name]
        self.framework.observe(self._charm.on.upgrade_charm, self._on_logging_relation_changed)
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)
        self.framework.observe(events.relation_departed, self._on_logging_relation_departed)

    def _on_logging_relation_changed(self, event: HookEvent):
        """Handle changes in related consumers.

        Anytime there are changes in the relation between Loki
        and its consumers charms.

        Args:
            event: a `CharmEvent` in response to which the consumer
                charm must update its relation data.

        Emits:
            loki_push_api_endpoint_joined: Once the relation is established, this event is emitted.
            loki_push_api_alert_rules_error: This event is emitted when an invalid alert rules
                file is encountered or if `alert_rules_path` is empty.
        """
        if isinstance(event, RelationEvent):
            self._process_logging_relation_changed(event.relation)
        else:
            # Upgrade event or other charm-level event
            for relation in self._charm.model.relations[self._relation_name]:
                self._process_logging_relation_changed(relation)

    def _reinitialize_alert_rules(self):
        """Reloads alert rules and updates all relations."""
        for relation in self._charm.model.relations[self._relation_name]:
            self._handle_alert_rules(relation)

    def _process_logging_relation_changed(self, relation: Relation):
        self._handle_alert_rules(relation)
        self.on.loki_push_api_endpoint_joined.emit()

    def _on_logging_relation_departed(self, _: RelationEvent):
        """Handle departures in related providers.

        Anytime there are departures in relations between the consumer charm and Loki
        the consumer charm is informed, through a `LokiPushApiEndpointDeparted` event.
        The consumer charm can then choose to update its configuration.
        """
        # Provide default to avoid throwing, as in some complicated scenarios with
        # upgrades and hook failures we might not have data in the storage
        self.on.loki_push_api_endpoint_departed.emit()

    @property
    def loki_endpoints(self) -> List[dict]:
        """Fetch Loki Push API endpoints sent from LokiPushApiProvider through relation data.

        Returns:
            A list with Loki Push API endpoints.
        """
        endpoints = []  # type: list
        for relation in self._charm.model.relations[self._relation_name]:
            endpoints = endpoints + json.loads(relation.data[relation.app].get("endpoints", "[]"))
        return endpoints


class ContainerNotFoundError(Exception):
    """Raised if there is no container with the given name or the name is ambiguous."""

    def __init__(self):
        msg = (
            "No 'container_name' parameter has been specified; since this Charmed Operator"
            " is not running exactly one container, it must be specified which container"
            " to get logs from."
        )
        self.message = msg

        super().__init__(self.message)


class PromtailDigestError(EventBase):
    """Event emitted when there is an error with the Promtail binary file."""

    def __init__(self, handle, message):
        super().__init__(handle)
        self.message = message

    def snapshot(self):
        """Save message information."""
        return {"message": self.message}

    def restore(self, snapshot):
        """Restore message information."""
        self.message = snapshot["message"]


class LogProxyEndpointDeparted(EventBase):
    """Event emitted when a Log Proxy has departed."""


class LogProxyEndpointJoined(EventBase):
    """Event emitted when a Log Proxy joins."""


class LogProxyEvents(ObjectEvents):
    """Event descriptor for events raised by `LogProxyConsumer`."""

    promtail_digest_error = EventSource(PromtailDigestError)
    log_proxy_endpoint_departed = EventSource(LogProxyEndpointDeparted)
    log_proxy_endpoint_joined = EventSource(LogProxyEndpointJoined)


class LogProxyConsumer(ConsumerBase):
    """LogProxyConsumer class.

    The `LogProxyConsumer` object provides a method for attaching `promtail` to
    a workload in order to generate structured logging data from applications
    which traditionally log to syslog or do not have native Loki integration.
    The `LogProxyConsumer` can be instantiated as follows:

        self._log_proxy_consumer = LogProxyConsumer(self, log_files=["/var/log/messages"])

    Args:
        charm: a `CharmBase` object that manages this `LokiPushApiConsumer` object.
            Typically this is `self` in the instantiating class.
        log_files: a list of log files to monitor with Promtail.
        relation_name: the string name of the relation interface to look up.
            If `charm` has exactly one relation with this interface, the relation's
            name is returned. If none or multiple relations with the provided interface
            are found, this method will raise either an exception of type
            NoRelationWithInterfaceFoundError or MultipleRelationsWithInterfaceFoundError,
            respectively.
        enable_syslog: Whether or not to enable syslog integration.
        syslog_port: The port syslog is attached to.
        alert_rules_path: an optional path for the location of alert rules
            files. Defaults to "./src/loki_alert_rules",
            resolved from the directory hosting the charm entry file.
            The alert rules are automatically updated on charm upgrade.
        recursive: Whether or not to scan for rule files recursively.
        container_name: An optional container name to inject the payload into.

    Raises:
        RelationNotFoundError: If there is no relation in the charm's metadata.yaml
            with the same name as provided via `relation_name` argument.
        RelationInterfaceMismatchError: The relation with the same name as provided
            via `relation_name` argument does not have the `loki_push_api` relation
            interface.
        RelationRoleMismatchError: If the relation with the same name as provided
            via `relation_name` argument does not have the `RelationRole.provides`
            role.
    """

    on = LogProxyEvents()

    def __init__(
        self,
        charm,
        log_files: list = None,
        relation_name: str = DEFAULT_LOG_PROXY_RELATION_NAME,
        enable_syslog: bool = False,
        syslog_port: int = 1514,
        alert_rules_path: str = DEFAULT_ALERT_RULES_RELATIVE_PATH,
        recursive: bool = False,
        container_name: Optional[str] = None,
    ):
        super().__init__(charm, relation_name, alert_rules_path, recursive)
        self._charm = charm
        self._relation_name = relation_name
        self._container = self._get_container(container_name)
        self._container_name = self._get_container_name(container_name)
        self._log_files = log_files or []
        self._syslog_port = syslog_port
        self._is_syslog = enable_syslog
        self.topology = ProviderTopology.from_charm(charm)

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created)
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_departed, self._on_relation_departed)
        self.framework.observe(
            getattr(self._charm.on, "{}_pebble_ready".format(self._container_name)),
            self._on_pebble_ready,
        )

    def _on_pebble_ready(self, _: WorkloadEvent):
        """Event handler for `pebble_ready`."""
        if self.model.relations[self._relation_name] and not self._is_promtail_installed():
            self._setup_promtail()

    def _on_relation_created(self, _: RelationCreatedEvent) -> None:
        """Event handler for `relation_created`."""
        if not self._container.can_connect():
            return
        if not self._is_promtail_installed():
            self._setup_promtail()

    def _on_relation_changed(self, event: RelationEvent) -> None:
        """Event handler for `relation_changed`.

        Args:
            event: The event object `RelationChangedEvent`.
        """
        self._handle_alert_rules(event.relation)

        if not self._container.can_connect():
            return
        if self.model.relations[self._relation_name] and not self._is_promtail_installed():
            self._setup_promtail()
        else:
            new_config = self._promtail_config
            if new_config != self._current_config:
                self._container.push(WORKLOAD_CONFIG_PATH, yaml.safe_dump(new_config))
                self._container.restart(WORKLOAD_SERVICE_NAME)
                self.on.log_proxy_endpoint_joined.emit()

    def _on_relation_departed(self, _: RelationEvent) -> None:
        """Event handler for `relation_departed`.

        Args:
            event: The event object `RelationDepartedEvent`.
        """
        if not self._container.can_connect():
            return
        if not self._charm.model.relations[self._relation_name]:
            self._container.stop(WORKLOAD_SERVICE_NAME)
            return

        new_config = self._promtail_config
        if new_config != self._current_config:
            self._container.push(WORKLOAD_CONFIG_PATH, yaml.safe_dump(new_config))

        if new_config["clients"]:
            self._container.restart(WORKLOAD_SERVICE_NAME)
        else:
            self._container.stop(WORKLOAD_SERVICE_NAME)
        self.on.log_proxy_endpoint_departed.emit()

    def _get_container(self, container_name: Optional[str] = "") -> Container:
        """Gets a single container by name or using the only container running in the Pod.

        If there is more than one container in the Pod a `PromtailDigestError` is emitted.

        Args:
            container_name: The container name.

        Returns:
            container: a `ops.model.Container` object representing the container.

        Raises:
            ContainerNotFoundError if no container_name was specified
        """
        if container_name:
            try:
                return self._charm.unit.get_container(container_name)
            except ModelError as e:
                msg = str(e)
                logger.warning(msg)
                self.on.promtail_digest_error.emit(msg)
        else:
            containers = dict(self._charm.model.unit.containers)

            if len(containers) == 1:
                return self._charm.unit.get_container([*containers].pop())

            raise ContainerNotFoundError

    def _get_container_name(self, container_name: Optional[str] = "") -> str:
        """Gets a container_name.

        If there is more than one container in the Pod a `ContainerNotFoundError` is raised.

        Args:
            container_name: The container name.

        Returns:
            container_name: a string representing the container_name.

        Raises:
            ContainerNotFoundError if no container_name was specified
        """
        if container_name:
            return container_name

        containers = dict(self._charm.model.unit.containers)
        if len(containers) == 1:
            return "".join(list(containers.keys()))

        raise ContainerNotFoundError

    def _add_pebble_layer(self) -> None:
        """Adds Pebble layer that manages Promtail service in Workload container."""
        pebble_layer = {
            "summary": "promtail layer",
            "description": "pebble config layer for promtail",
            "services": {
                WORKLOAD_SERVICE_NAME: {
                    "override": "replace",
                    "summary": WORKLOAD_SERVICE_NAME,
                    "command": "{} {}".format(WORKLOAD_BINARY_PATH, self._cli_args),
                    "startup": "disabled",
                }
            },
        }
        self._container.add_layer(self._container_name, pebble_layer, combine=True)

    def _create_directories(self) -> None:
        """Creates the directories for Promtail binary and config file."""
        self._container.make_dir(path=WORKLOAD_BINARY_DIR, make_parents=True)
        self._container.make_dir(path=WORKLOAD_CONFIG_DIR, make_parents=True)

    def _obtain_promtail(self) -> None:
        """Obtain promtail binary from an attached resource or download it."""
        if self._is_promtail_attached():
            return

        if self._promtail_must_be_downloaded():
            self._download_and_push_promtail_to_workload()
        else:
            self._push_binary_to_workload()

    def _push_binary_to_workload(self, resource_path: str = BINARY_PATH) -> None:
        with open(resource_path, "rb") as f:
            self._container.push(WORKLOAD_BINARY_PATH, f, permissions=0o755, make_dirs=True)
            logger.debug("The promtail binary file has been pushed to the workload container.")

    def _is_promtail_attached(self) -> bool:
        """Checks whether Promtail binary is attached to the charm or not.

        Returns:
            a boolean representing whether Promtail binary is attached or not.
        """
        try:
            resource_path = self._charm.model.resources.fetch("promtail-bin")
        except ModelError:
            return False
        except NameError as e:
            if "invalid resource name" in str(e):
                return False
            else:
                raise

        logger.info("Promtail binary file has been obtained from an attached resource.")
        self._push_binary_to_workload(resource_path)
        return True

    def _promtail_must_be_downloaded(self) -> bool:
        """Checks whether promtail binary must be downloaded or not.

        Returns:
            a boolean representing whether Promtail binary must be downloaded or not.
        """
        if not self._is_promtail_binary_in_charm():
            return True

        if not self._sha256sums_matches(BINARY_PATH, BINARY_SHA256SUM):
            return True

        logger.debug("Promtail binary file is already in the the charm container.")
        return False

    def _sha256sums_matches(self, file_path: str, sha256sum: str) -> bool:
        """Checks whether a file's sha256sum matches or not with an specific sha256sum.

        Args:
            file_path: A string representing the files' patch.
            sha256sum: The sha256sum against which we want to verify.

        Returns:
            a boolean representing whether a file's sha256sum matches or not with
            an specific sha256sum.
        """
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                result = sha256(file_bytes).hexdigest()

                if result != sha256sum:
                    msg = "File sha256sum mismatch, expected:'{}' but got '{}'".format(
                        sha256sum, result
                    )
                    logger.debug(msg)
                    return False

                return True
        except (APIError, FileNotFoundError):
            msg = "File: '{}' could not be opened".format(file_path)
            logger.error(msg)
            return False

    def _is_promtail_binary_in_charm(self) -> bool:
        """Check if Promtail binary is already stored in charm container.

        Returns:
            a boolean representing whether Promtail is present or not.
        """
        return True if Path(BINARY_PATH).is_file() else False

    def _download_and_push_promtail_to_workload(self) -> None:
        """Downloads a Promtail zip file and pushes the binary to the workload."""
        # Use the first
        relations = self._charm.model.relations[self._relation_name]
        if len(relations) > 1:
            logger.debug(
                "Multiple log_proxy relations. Getting Promtail from application {}".format(
                    relations[0].app.name
                )
            )
        url = relations[0].data[relations[0].app].get("promtail_binary_zip_url")

        with urlopen(url) as r:
            file_bytes = r.read()
            with open(BINARY_ZIP_PATH, "wb") as f:
                f.write(file_bytes)
                logger.info(
                    "Promtail binary zip file has been downloaded and stored in: %s",
                    BINARY_ZIP_PATH,
                )

            ZipFile(BytesIO(file_bytes)).extractall(BINARY_DIR)
            logger.debug("Promtail binary file has been downloaded.")

        self._push_binary_to_workload()

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

    @property
    def _promtail_config(self) -> dict:
        """Generates the config file for Promtail."""
        config = {"clients": self._clients_list()}
        config.update(self._server_config())
        config.update(self._positions())
        config.update(self._scrape_configs())
        return config

    def _clients_list(self) -> list:
        """Generates a list of clients for use in the promtail config.

        Returns:
            A list of endpoints
        """
        clients = []  # type: list
        for relation in self._charm.model.relations.get(self._relation_name, []):
            clients = clients + json.loads(relation.data[relation.app]["endpoints"])
        return clients

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
        job_name = "juju_{}".format(self.topology.identifier)
        common_labels = self.topology.as_promql_label_dict()
        scrape_configs = []

        # Files config
        labels = common_labels.copy()
        labels.update(
            {
                "job": job_name,
                "__path__": "",
            }
        )
        config = {"targets": ["localhost"], "labels": labels}
        scrape_config = {
            "job_name": "system",
            "static_configs": self._generate_static_configs(config),
        }
        scrape_configs.append(scrape_config)

        # Syslog config
        if self._is_syslog:
            syslog_labels = common_labels.copy()
            syslog_labels.update({"job": "{}_syslog".format(job_name)})
            syslog_config = {
                "job_name": "syslog",
                "syslog": {
                    "listen_address": "127.0.0.1:{}".format(self._syslog_port),
                    "label_structured_data": True,
                    "labels": syslog_labels,
                },
            }
            scrape_configs.append(syslog_config)  # type: ignore

        return {"scrape_configs": scrape_configs}

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

    def _setup_promtail(self) -> None:
        relation = self._charm.model.relations[self._relation_name][0]
        if relation.data[relation.app].get("promtail_binary_zip_url", None) is None:
            return
        self._create_directories()
        self._container.push(
            WORKLOAD_CONFIG_PATH, yaml.safe_dump(self._promtail_config), make_dirs=True
        )
        self._add_pebble_layer()
        try:
            self._obtain_promtail()
        except HTTPError as e:
            msg = "Promtail binary couldn't be download - {}".format(str(e))
            logger.warning(msg)
            self.on.promtail_digest_error.emit(msg)
        if self._current_config["clients"]:
            self._container.restart(WORKLOAD_SERVICE_NAME)
            self.on.log_proxy_endpoint_joined.emit()

    def _is_promtail_installed(self) -> bool:
        """Determine if promtail has already been installed to the container."""
        try:
            self._container.list_files(WORKLOAD_BINARY_PATH)
        except (APIError, FileNotFoundError):
            return False
        return True

    @property
    def syslog_port(self) -> str:
        """Gets the port on which promtail is listening for syslog.

        Returns:
            A str representing the port
        """
        return str(self._syslog_port)

    @property
    def rsyslog_config(self) -> str:
        """Generates a config line for use with rsyslog.

        Returns:
            The rsyslog config line as a string
        """
        return 'action(type="omfwd" protocol="tcp" target="127.0.0.1" port="{}" Template="RSYSLOG_SyslogProtocol23Format" TCP_Framing="octet-counted")'.format(
            self._syslog_port
        )
