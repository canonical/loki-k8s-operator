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
   from charms.loki_k8s.v0.log_proxy import LogProxyConsumer, PromtailDigestError

   ...

       def __init__(self, *args):
           ...
           try:
               self._log_proxy = LogProxyConsumer(
                   charm=self, log_files=LOG_FILES, container_name=PEER, enable_syslog=True
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

The object can raise a `PromtailDigestError` when:

- Promtail binary cannot be downloaded.
- No `container_name` parameter has been specified and the Pod has more than 1 container.
- The sha256 sum mismatch for promtail binary.

that's why in the above example, the instantiation is made in a `try/except` block
to handle these situations conveniently.

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
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

import yaml
from ops.charm import (
    CharmBase,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationEvent,
    RelationRole,
)
from ops.framework import (
    EventBase,
    EventSource,
    Object,
    ObjectEvents,
    StoredDict,
    StoredList,
    StoredState,
)
from ops.model import ModelError, Relation

# The unique Charmhub library identifier, never change it
LIBID = "bf76f23cdd03464b877c52bd1d2f563e"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 8

logger = logging.getLogger(__name__)

RELATION_INTERFACE_NAME = "loki_push_api"
DEFAULT_RELATION_NAME = "logging"
DEFAULT_ALERT_RULES_RELATIVE_PATH = "./src/loki_alert_rules"

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


def _is_valid_rule(rule: dict, allow_free_standing: bool) -> bool:
    """This method validates if an alert rule is well formed.

    Args:
        rule: A dictionary containing an alert rule definition

    Returns:
        True if the alert rule is well formed; False otherwise.
    """
    mandatory = ["alert", "expr"]
    if any(field not in rule for field in mandatory):
        return False

    if not allow_free_standing and "%%juju_topology%%" not in rule["expr"]:
        return False

    return True


def _type_convert_stored(obj):
    """Convert Stored* to their appropriate types, recursively."""
    if isinstance(obj, StoredList):
        return list(map(_type_convert_stored, obj))
    elif isinstance(obj, StoredDict):
        rdict = {}  # type: Dict[Any, Any]
        for k in obj.keys():
            rdict[k] = _type_convert_stored(obj[k])
        return rdict
    else:
        return obj


class JujuTopology:
    """Class for storing and formatting juju topology information."""

    def __init__(self, model: str, model_uuid: str, application: str, charm_name: str):
        self.model = model
        self.model_uuid = model_uuid
        self.application = application
        self.charm_name = charm_name

    @classmethod
    def from_charm(cls, charm):
        """Factory method for creating the topology dataclass from a given charm."""
        return cls(
            model=charm.model.name,
            model_uuid=charm.model.uuid,
            application=charm.model.app.name,
            charm_name=charm.meta.name,
        )

    @classmethod
    def from_relation_data(cls, data):
        """Factory method for creating the topology dataclass from a relation data dict."""
        return cls(
            model=data["model"],
            model_uuid=data["model_uuid"],
            application=data["application"],
            charm_name=data["charm_name"],
        )

    @property
    def identifier(self) -> str:
        """Format the topology information into a terse string."""
        return "{}_{}_{}".format(self.model, self.model_uuid, self.application)

    @property
    def short_model_uuid(self):
        """Obtain the short form of the model uuid."""
        return self.model_uuid[:7]

    @property
    def scrape_identifier(self):
        """Format the topology information into a scrape identifier."""
        return "juju_{}_{}_{}".format(
            self.model,
            self.short_model_uuid,
            self.application,
        )

    @property
    def logql_labels(self) -> str:
        """Format the topology information into a verbose string."""
        return 'juju_model="{}", juju_model_uuid="{}", juju_application="{}"'.format(
            self.model, self.model_uuid, self.application
        )

    def as_dict(self, short_uuid=False) -> dict:
        """Format the topology information into a dict."""
        return {
            "model": self.model,
            "model_uuid": self.model_uuid,
            "application": self.application,
            "charm_name": self.charm_name,
        }

    def as_dict_with_logql_labels(self):
        """Format the topology information into a dict with keys having 'juju_' as prefix."""
        return {
            "juju_model": self.model,
            "juju_model_uuid": self.model_uuid,
            "juju_application": self.application,
            "juju_charm": self.charm_name,
        }

    def render(self, template: str):
        """Render a juju-topology template string with topology info."""
        return template.replace("%%juju_topology%%", self.logql_labels)


def load_alert_rule_from_file(
    path: Path, topology: JujuTopology, allow_free_standing
) -> Optional[dict]:
    """Load alert rule from a rules file.

    Args:
        path: path to a *.rule file with a single rule ("groups" super section omitted).
        topology: a `JujuTopology` instance.
        allow_free_standing: whether or not to reject files that do not have the special
          %%juju_topology%% template variable, which is the case for free-standing rules.
    """
    with path.open() as rule_file:
        # Load a list of rules from file then add labels and filters
        try:
            rule = yaml.safe_load(rule_file)
            if not _is_valid_rule(rule, allow_free_standing):
                return None
        except Exception as e:
            logger.error("Failed to read alert rules from %s: %s", path.name, e)
            return None
        else:
            # add "juju_" topology labels
            if "labels" not in rule:
                rule["labels"] = {}
            rule["labels"].update(topology.as_dict_with_logql_labels())

            # insert juju topology filters into a Loki alert rule
            rule["expr"] = topology.render(rule["expr"])

            return rule


def load_alert_rules_from_dir(
    dir_path: str,
    topology: JujuTopology,
    *,
    recursive: bool = False,
    allow_free_standing: bool = False,
) -> Tuple[List[dict], List[Path]]:
    """Load alert rules from rule files.

    All rules from files for the same directory are loaded into a single
    group. The generated name of this group includes juju topology.
    By default, only the top directory is scanned; for nested scanning, pass `recursive=True`.

    Args:
        dir_path: directory containing *.rule files (alert rules without groups).
        topology: a `JujuTopology` instance.
        recursive: flag indicating whether to scan for rule files recursively.
        allow_free_standing: whether or not to reject files that do not have the special
          %%juju_topology%% template variable, which is the case for free-standing rules.

    Returns:
        A 2-tuple consisting:
        - a list of prometheus alert rule groups
        - a list of invalid rules files
    """
    alerts = defaultdict(list)

    def _group_name(path) -> str:
        """Generate group name from path and topology.

        The group name is made up of the relative path between the root dir_path, the file path,
        and topology identifier.

        Args:
            path: path to rule file.
        """
        relpath = os.path.relpath(os.path.dirname(path), dir_path)

        # Generate group name:
        #  - name, from juju topology
        #  - suffix, from the relative path of the rule file;
        return "{}_{}alerts".format(
            topology.identifier, "" if relpath == "." else relpath.replace(os.path.sep, "_") + "_"
        )

    invalid_files = []
    for path in filter(Path.is_file, Path(dir_path).glob("**/*.rule" if recursive else "*.rule")):
        rule = load_alert_rule_from_file(path, topology, allow_free_standing)

        if rule:
            logger.debug("Reading alert rule from %s", path)
            alerts[_group_name(path)].append(rule)
        else:
            invalid_files.append(path)

    # Gather all alerts into a list of groups since Prometheus
    # requires alerts be part of some group
    groups = [{"name": k, "rules": v} for k, v in alerts.items()]
    return groups, invalid_files


def _resolve_dir_against_charm_path(charm: CharmBase, *path_elements: str) -> str:
    """Resolve the provided path items against the directory of the main file.

    Look up the directory of the main .py file being executed. This is normally
    going to be the charm.py file of the charm including this library. Then, resolve
    the provided path elements and return its absolute path, without checking for existence or
     validity.
    """
    charm_dir = Path(charm.charm_dir)
    if not charm_dir.exists() or not charm_dir.is_dir():
        # Operator Framework does not currently expose a robust
        # way to determine the top level charm source directory
        # that is consistent across deployed charms and unit tests
        # Hence for unit tests the current working directory is used
        # TODO: updated this logic when the following ticket is resolved
        # https://github.com/canonical/operator/issues/643
        charm_dir = Path(os.getcwd())

    alerts_dir_path = charm_dir.absolute().joinpath(*path_elements)
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
                relation_interface, charm.name
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


class LokiPushApiAlertRulesError(EventBase):
    """Event emitted when an AlertRulesError exception is raised."""

    def __init__(self, handle, message):
        super().__init__(handle)
        self.message = message

    def snapshot(self):
        """Save message information."""
        return {"message": self.message}

    def restore(self, snapshot):
        """Restore message information."""
        self.message = snapshot["message"]


class LokiPushApiEndpointDeparted(EventBase):
    """Event emitted when Loki departed."""


class LokiPushApiEndpointJoined(EventBase):
    """Event emitted when Loki joined."""


class LoggingEvents(ObjectEvents):
    """Event descriptor for events raised by `LokiPushApiProvider`."""

    loki_push_api_alert_rules_error = EventSource(LokiPushApiAlertRulesError)
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
        self.container.make_dir(self._rules_dir, make_parents=True)

        events = self._charm.on[relation_name]
        self.framework.observe(self._charm.on.upgrade_charm, self._on_logging_relation_changed)
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)
        self.framework.observe(events.relation_departed, self._on_logging_relation_departed)

    def _on_logging_relation_changed(self, event):
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
            relation.data[self._charm.app].update({"loki_push_api": self._loki_push_api})
            relation.data[self._charm.app].update({"data": self._promtail_binary_url})
            logger.debug("Saved Loki url in relation data %s", self._loki_push_api)

        if relation.data.get(relation.app).get("alert_rules"):
            logger.debug("Saved alerts rules to disk")
            self._remove_alert_rules_files(self.container)
            self._generate_alert_rules_files(self.container)

    def _on_logging_relation_departed(self, event):
        """Removes alert rules files when consumer charms left the relation with Loki.

        Args:
            event: a `CharmEvent` in response to which the Loki
                charm must update its relation data.
        """
        if event.relation.data.get(event.relation.app):
            self._remove_alert_rules_files(self.container)

    @property
    def _promtail_binary_url(self) -> str:
        """URL from which Promtail binary can be downloaded."""
        return json.dumps({"promtail_binary_zip_url": PROMTAIL_BINARY_ZIP_URL})

    @property
    def _loki_push_api(self) -> str:
        """Fetch Loki push API URL.

        Returns:
            Loki push API URL as json string
        """
        endpoint_url = "http://{}:{}/loki/api/v1/push".format(self.unit_ip, self.port)
        return json.dumps({"url": endpoint_url})

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP."""
        bind_address = self._charm.model.get_binding(self._relation_name).network.bind_address

        if bind_address:
            return str(bind_address)
        return ""

    def _remove_alert_rules_files(self, container) -> None:
        """Remove alert rules files from workload container.

        Args:
            container: Container which has alert rules files to be deleted
        """
        container.remove_path(self._rules_dir, recursive=True)
        logger.debug("Previous Alert rules files deleted")
        # Since container.remove_path deletes the directory itself with its files
        # we should create it again.
        os.makedirs(self._rules_dir, exist_ok=True)

    def _generate_alert_rules_files(self, container) -> None:
        """Generate and upload alert rules files.

        Args:
            container: Container into which alert rules files are going to be uploaded
        """
        for rel_id, alert_rules in self.alerts().items():
            filename = "{}_rel_{}_alert.rules".format(
                JujuTopology.from_relation_data(alert_rules).identifier,
                rel_id,
            )
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
        alerts = {}
        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.units:
                continue

            alert_rules = json.loads(relation.data[relation.app].get("alert_rules", "{}"))
            metadata = json.loads(relation.data[relation.app].get("metadata", "{}"))

            if alert_rules and metadata:
                try:
                    alerts[relation.id] = JujuTopology.from_relation_data(metadata).as_dict(
                        short_uuid=True
                    )
                    alerts[relation.id].update(groups=alert_rules["groups"])

                except KeyError as e:
                    logger.error(
                        "Relation %s has invalid data: '%s' key is missing",
                        relation.id,
                        e,
                    )

        return alerts


class ConsumerBase(RelationManagerBase):
    """Consumer's base class."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        alert_rules_path: str = DEFAULT_ALERT_RULES_RELATIVE_PATH,
        allow_free_standing_rules: bool = False,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self.allow_free_standing_rules = allow_free_standing_rules
        self._alert_rules_path = _resolve_dir_against_charm_path(charm, alert_rules_path)
        self.topology = JujuTopology.from_charm(charm)

    def _handle_alert_rules(self, relation):
        if self._charm.unit.is_leader():
            alert_groups, invalid_files = load_alert_rules_from_dir(
                self._alert_rules_path,
                self.topology,
                recursive=False,
                allow_free_standing=self.allow_free_standing_rules,
            )
            alert_rules_error_message = self._check_alert_rules(alert_groups, invalid_files)

            if alert_rules_error_message:
                self.on.loki_push_api_alert_rules_error.emit(alert_rules_error_message)

            relation.data[self._charm.app]["metadata"] = json.dumps(self.topology.as_dict())
            relation.data[self._charm.app]["alert_rules"] = json.dumps({"groups": alert_groups})

    def _check_alert_rules(self, alert_groups, invalid_files) -> str:
        """Check alert rules.

        Args:
            alert_groups: a list of prometheus alert rule groups.
            invalid_files: a list of invalid rules files.

        Returns:
            A string with the validation message. The message is not empty whether there are
            invalid alert rules files or there are no alert rules groups.
        """
        message = ""

        if invalid_files:
            must_contain = ["'alert'", "'expr'"]
            if not self.allow_free_standing_rules:
                must_contain.append("'%%juju_topology%%'")

            message = "Failed to read alert rules (must contain {}): ".format(
                ", ".join(must_contain)
            ) + ", ".join(map(str, invalid_files))
        elif not alert_groups:
            message = "No alert rules found in {}".format(self._alert_rules_path)

        return message


class LokiPushApiConsumer(ConsumerBase):
    """Loki Consumer class."""

    on = LoggingEvents()
    _stored = StoredState()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        alert_rules_path: str = DEFAULT_ALERT_RULES_RELATIVE_PATH,
        allow_free_standing_rules: bool = False,
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
            alert_rules_path: an optional path for the location of alert rules
                files. Defaults to "./src/loki_alert_rules",
                resolved from the directory hosting the charm entry file.
                The alert rules are automatically updated on charm upgrade.

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
        super().__init__(charm, relation_name, alert_rules_path, allow_free_standing_rules)
        self._stored.set_default(loki_push_api={})
        events = self._charm.on[relation_name]
        self.framework.observe(self._charm.on.upgrade_charm, self._on_logging_relation_changed)
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)
        self.framework.observe(events.relation_departed, self._on_logging_relation_departed)

    def _on_logging_relation_changed(self, event):
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

    def _process_logging_relation_changed(self, relation: Relation):
        loki_push_api_data = relation.data[relation.app].get("loki_push_api")

        if loki_push_api_data:
            self._stored.loki_push_api[relation.id] = json.loads(loki_push_api_data)

        self._handle_alert_rules(relation)
        self.on.loki_push_api_endpoint_joined.emit()

    def _on_logging_relation_departed(self, event):
        """Handle departures in related providers.

        Anytime there are departures in relations between the consumer charm and Loki
        the consumer charm is informed, through a `LokiPushApiEndpointDeparted` event.
        The consumer charm can then choose to update its configuration.
        """
        # Provide default to avoid throwing, as in some complicated scenarios with
        # upgrades and hook failures we might not have data in the storage
        self._stored.loki_push_api.pop(event.relation.id, None)
        self.on.loki_push_api_endpoint_departed.emit()

    @property
    def loki_push_api(self) -> List[str]:
        """Fetch Loki Push API endpoints sent from LokiPushApiProvider through relation data.

        Returns:
            A list with Loki Push API endpoints.
        """
        return [
            _type_convert_stored(loki_endpoint)
            for loki_endpoint in self._stored.loki_push_api.values()
        ]


class PromtailDigestError(Exception):
    """Raised if there is an error with Promtail binary file."""


class LogProxyConsumer(RelationManagerBase):
    """LogProxyConsumer class."""

    _stored = StoredState()

    def __init__(
        self,
        charm,
        log_files: list = [],
        container_name: Optional[str] = None,
        relation_name: str = "log_proxy",
        enable_syslog: bool = False,
        syslog_port: int = 1514,
    ):
        super().__init__(charm, relation_name)
        self._stored.set_default(grafana_agents="{}")
        self._charm = charm
        self._relation_name = relation_name
        self._container = self._get_container(container_name)
        self._container_name = self._get_container_name(container_name)
        self._log_files = log_files
        self._syslog_port = syslog_port
        self._is_syslog = enable_syslog
        self.topology = JujuTopology.from_charm(charm)

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
        if event.relation.data[event.app].get("data", None):
            try:
                self._obtain_promtail(event)
            except HTTPError as e:
                msg = "Promtail binary couldn't be download - {}".format(str(e))
                logger.warning(msg)
                raise PromtailDigestError(msg)
            else:
                self._update_config(event)
                self._update_agents_list(event)
                self._add_pebble_layer()
                self._container.restart(WORKLOAD_SERVICE_NAME)

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
                "No 'container_name' parameter has been specified; since this Charmed Operator"
                " is not running exactly one container, it must be specified which container"
                " to get logs from."
            )
            raise PromtailDigestError(msg)

    def _get_container_name(self, container_name):
        """Gets a container_name.

        If there is more than one container in the Pod a `PromtailDigestError` is raised.

        Args:
            container_name: The container name.

        Returns:
            container_name: a string representing the container_name.

        Raises:
            PromtailDigestError if no `container_name` is passed and there is more than one
                container in the Pod.
        """
        if container_name is not None:
            return container_name

        containers = dict(self._charm.model.unit.containers)
        if len(containers) == 1:
            return "".join(list(containers.keys()))

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
        """Obtain promtail binary from an attached resource or download it."""
        if self._is_promtail_attached():
            return

        if self._promtail_must_be_downloaded():
            self._download_and_push_promtail_to_workload(event)
        else:
            self._push_binary_to_workload()

    def _push_binary_to_workload(self, resource_path=BINARY_PATH) -> None:
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
        except FileNotFoundError:
            msg = "File: '{}' could not be opened".format(file_path)
            logger.error(msg)
            return False

    def _is_promtail_binary_in_charm(self) -> bool:
        """Check if Promtail binary is already stored in charm container.

        Returns:
            a boolean representing whether Promtail is present or not.
        """
        return True if Path(BINARY_PATH).is_file() else False

    def _download_and_push_promtail_to_workload(self, event) -> None:
        """Downloads a Promtail zip file and pushes the binary to the workload."""
        url = json.loads(event.relation.data[event.app].get("data"))["promtail_binary_zip_url"]

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

    def _update_agents_list(self, event):
        """Updates the active Grafana agents list.

        Args:
            event: The event object `RelationChangedEvent` or `RelationDepartedEvent`
        """
        grafana_agents = json.loads(self._stored.grafana_agents)

        if isinstance(event, RelationChangedEvent):
            agent_url = json.loads(event.relation.data[event.app].get("loki_push_api"))["url"]
            grafana_agents[str(event.app)] = agent_url
            self._stored.grafana_agents = json.dumps(grafana_agents)
        elif isinstance(event, RelationDepartedEvent):
            agent_url = grafana_agents.pop(str(event.app))
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
            agent_url = json.loads(event.relation.data[event.app].get("loki_push_api"))["url"]
            config = self._add_client(current_config, agent_url)
        elif isinstance(event, RelationDepartedEvent):
            agent_url = json.loads(self._stored.grafana_agents)[str(event.app)]
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
        job_name = "juju_{}_{}_{}".format(
            self._charm.model.name, self._charm.model.uuid, self._charm.model.app.name
        )
        common_labels = self.topology.as_dict_with_logql_labels()
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

    @property
    def syslog_port(self):
        """Gets the port on which promtail is listening for syslog.

        Returns:
            A string representing the port
        """
        return self._syslog_port

    @property
    def rsyslog_config(self):
        """Generates a config line for use with rsyslog.

        Returns:
            The rsyslog config line as a string
        """
        return 'action(type="omfwd" protocol="tcp" target="127.0.0.1" port="{}" Template="RSYSLOG_SyslogProtocol23Format" TCP_Framing="octet-counted")'.format(
            self._syslog_port
        )
