#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""## Overview.

This document explains how to integrate with the Loki charm.
It also explains how alternative implementations of the Loki charm
may maintain the same interface and be backward compatible with all
currently integrated charms. Finally this document is the
authoritative reference on the structure of relation data that is
shared between Loki charms and any other charm that intends to
provide a scrape target for Loki.

## Provider Library Usage

This object may be used by Loki charms to manage relations
with their clients.
For this purposes a Loki charm needs to instantiate the
`LokiProvider` object providing it with two pieces
of information:

- A reference to the parent (Loki) charm.

- Name of the relation that the Loki charm uses to interact with
  its clients. This relation name must match the one used in `metadata.yaml`
  for the `loki_push_api` interface.

For example a Loki charm may instantiate the
`LokiProvider` in its constructor as follows

    from charms.loki_k8s.v0.loki import LokiProvider
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
                self.loki_provider = LokiProvider(self, "logging")
                logger.debug("Loki Provider is available. Loki version: %s", version)
            except LokiServerNotReadyError as e:
                self.unit.status = MaintenanceStatus(str(e))
            except LokiServerError as e:
                self.unit.status = BlockedStatus(str(e))


The `LokiProvider` object has two main responsabilities:

1.- Be in charge of setting the Loki Push API Address into
relation data so clients can use it to send logs. Every time a unit joins
a relation: `$ juju add-relation loki-k8s loki-client-k8s` the object sets:

    event.relation.data[self.charm.unit]["data"] = self._loki_push_api

Where `self._loki_push_api` is: `http://<LOKI_UNIT_IP>:<LOKI_PORT>/loki/api/v1/push`


2.- Every time a Loki client unit joins a relation set its metadata and
[alerts rules](https://grafana.com/docs/loki/latest/rules/#alerting-rules) to
relation data.

The metadata is stored in relation data:

    event.relation.data[self._charm.app]["metadata"] = json.dumps(self._scrape_metadata)

For instance the metadata has the following data:

    {'model': 'loki',
     'model_uuid': '0b7d1071-ded2-4bf5-80a3-10a81aeb1386',
     'application': 'promtail-k8s'
    }

About alert rules, they are stored in relation data:

    if alert_groups := self._labeled_alert_groups:
        event.relation.data[self._charm.app]["alert_rules"] = json.dumps(
            {"groups": alert_groups}
        )


And has this aspect:

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


Once these alert rules are sent over relation data, the `LokiProvider` object
stores these files in the directory `/loki/rules` inside the Loki charm container.


## Consumer Library Usage

This Loki charm interacts with its clients using the Loki
charm library. Charms seeking to send log to Loki,
must do so using the `LokiConsumer` object from this charm library.
For the simplest use cases, using the `LokiConsumer` object only requires
instantiating it, typically in the constructor of your charm (the one which
sends logs).

    from charms.loki_k8s.v0.loki import LokiConsumer

    class LokiClientCharm(CharmBase):

        def __init__(self, *args):
            super().__init__(*args)
            ...
            self.loki = LokiConsumer(self, "logging")


The `LokiConsumer` constructor requires two things:

- A reference to the parent (LokiClientCharm) charm.

- Name of the relation that the Loki charm uses to interact with
  its clients. This relation name must match the relation in metadata.yaml
  used for the `loki_push_api` interface.


## Alerting Rules

This charm library also supports gathering alerting rules from all
related Loki clients charms and enabling corresponding alerts within the
Loki charm. Alert rules are automatically gathered by `LokiConsumer` object
from a directory conventionally named `loki_alert_rules`.
This directory must reside at the top level in the `src` folder of the
consumer charm. Each file in this directory is assumed to be a single alert rule
in YAML format. The file name must have the `.rule` extension.
The format of this alert rule conforms to the
[Loki docs](https://grafana.com/docs/loki/latest/rules/#alerting-rules).
An example of the contents of one such file is shown below.

```
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

It is **critical** to use the `%%juju_topology%%` filter in the
expression for the alert rule shown above. This filter is a stub that
is automatically replaced by the `LokiConsumer` following Loki Client's Juju
topology (application, model and its UUID). Such a topology filter is
essential to ensure that alert rules submitted by one provider charm
generates alerts only for that same charm.  The Loki charm may
be related to multiple Loki client charms. Without this, filter
rules submitted by one provider charm will also result in
corresponding alerts for other provider charms. Hence every alert rule
expression must include such a topology filter stub.

Gathering alert rules and generating rule files within the Loki
charm is easily done using the `alerts()` method of
`LokiProvider`. Alerts generated by Loki will
automatically include Juju topology labels in the alerts. These labels
indicate the source of the alert. The following lables are
automatically added to every alert

- `juju_model`
- `juju_model_uuid`
- `juju_application`

## Relation Data

The Loki charm uses both application and unit relation data to
obtain information regarding Loki Push API and alert rules.

Units of consumer charm send their alert rules over app relation
data using the `alert_rules` key.

"""

import json
import logging
import os
from pathlib import Path

import yaml
from ops.charm import CharmBase
from ops.framework import Object, StoredState
from ops.model import BlockedStatus

# The unique Charmhub library identifier, never change it
LIBID = "bf76f23cdd03464b877c52bd1d2f563e"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3

# Alert rules directory in workload container
RULES_DIR = "/loki/rules"

logger = logging.getLogger(__name__)


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


class AlertRuleError(Exception):
    """Custom exception to indicate that alert rule is not well formed"""

    def __init__(self, message="Alert rule is not well formed"):
        self.message = message
        super().__init__(self.message)


class LokiProvider(RelationManagerBase):
    """A LokiProvider class"""

    def __init__(self, charm, relation_name: str):
        """A Loki service provider.

        Args:

            charm: a `CharmBase` instance that manages this
                instance of the Loki service.
            relation_name: string name of the relation that provides the
                Loki logging service.
        """
        super().__init__(charm, relation_name)
        self.charm = charm
        self._relation_name = relation_name
        self.container = self.charm.unit.get_container("loki")
        events = self.charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)
        self.framework.observe(events.relation_departed, self._on_logging_relation_departed)

    def _on_logging_relation_changed(self, event):
        """Handle changes in related consumers.

        Anytime there are changes in relations between Loki
        and its consumers charms, Loki set the `loki_push_api`
        into the relation data.
        Besides Loki generates alert rules files based what
        consumer charms forwards,

        Args:
            event: a `CharmEvent` in response to which the Loki
                charm must update its relation data.
        """

        if event.relation.data[self.charm.unit].get("data") is None:
            event.relation.data[self.charm.unit].update({"data": self._loki_push_api})
            logger.debug("Saving Loki url in relation data %s", self._loki_push_api)

        if event.relation.data.get(event.relation.app).get("alert_rules") is not None:
            logger.debug("Saving alerts rules to disk")
            self._remove_alert_rules_files(self.container)
            self._generate_alert_rules_files(self.container)

    def _on_logging_relation_departed(self, event):
        """Removes alert rules files when consumer charms
        left the relation with Loki

        Args:
            event: a `CharmEvent` in response to which the Loki
                charm must update its relation data.
        """
        if event.relation.data.get(event.relation.app):
            self._remove_alert_rules_files(self.container)

    @property
    def _loki_push_api(self) -> str:
        """Fetch Loki push API URL

        Returns:
            Loki push API URL as json string"""

        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP"""
        if bind_address := self.charm.model.get_binding(self._relation_name).network.bind_address:
            return str(bind_address)
        return ""

    def _remove_alert_rules_files(self, container) -> None:
        """Remove alert rules files from worload container RULES_DIR

        Args:
            container: Container which has alert rules files to be deleted
        """

        container.remove_path(RULES_DIR, recursive=True)
        logger.debug("Previous Alert rules files deleted")
        # Since container.remove_path deletes the directory itself with its files
        # we should create it again.
        os.makedirs(RULES_DIR, exist_ok=True)

    def _generate_alert_rules_files(self, container) -> None:
        """Generate and upload alert rules files

        Args:
            container: Container into which alert rules files are going to be uploaded
        """

        for rel_id, alert_rules in self.alerts().items():
            filename = "juju_{}_{}_{}_rel_{}_alert.rules".format(
                alert_rules["model"],
                alert_rules["model_uuid"],
                alert_rules["application"],
                rel_id,
            )
            path = os.path.join(RULES_DIR, filename)
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
        for relation in self.charm.model.relations[self._relation_name]:
            if not relation.units:
                continue

            alert_rules = json.loads(relation.data[relation.app].get("alert_rules", "{}"))
            metadata = json.loads(relation.data[relation.app].get("metadata", "{}"))

            if alert_rules and metadata:
                try:
                    alerts[relation.id] = {
                        "groups": alert_rules["groups"],
                        "model": metadata["model"],
                        "model_uuid": metadata["model_uuid"][:7],
                        "application": metadata["application"],
                    }
                except KeyError as e:
                    logger.error(
                        "Relation %s has invalid data: '%s' key is missing",
                        relation.id,
                        e,
                    )

        return alerts


class LokiConsumer(RelationManagerBase):
    """
    Loki Consumer class
    """

    _stored = StoredState()
    _ALERT_RULES_PATH: str

    def __init__(
        self, charm: CharmBase, relation_name: str, alert_rules_path="src/loki_alert_rules"
    ):
        """Construct a Loki charm client.

        The `LokiConsumer` object provides configurations to a Loki client charm.
        A charm instantiating this object needs Loki information, for instance the
        Loki API endpoint to push logs.
        The `LokiConsumer` can be instantiated as follows:

            self.loki_consumer = LokiConsumer(self, relation_name="logging")

        Args:

            charm: a `CharmBase` object that manages this
                `LokiConsumer` object. Typically this is
                `self` in the instantiating class.
            relation_ name: a string name of the relation between `charm` and
                the Loki charmed service.
            alert_rules_path: an optional path for the location of alert rules
                files.  Defaults to "src/loki_alert_rules" at the top level
                of the charm repository.
        """
        super().__init__(charm, relation_name)
        self._stored.set_default(loki_push_api=None)
        self._charm = charm
        self._relation_name = relation_name
        self._ALERT_RULES_PATH = alert_rules_path
        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_logging_relaton_changed)

    def _on_logging_relaton_changed(self, event):
        """Handle changes in related consumers.

        Anytime there are changes in the relation between Loki
        and its consumers charms,

        Args:
            event: a `CharmEvent` in response to which the consumer
                charm must update its relation data.
        """
        if not self._charm.unit.is_leader():
            return

        if event.unit is None:
            # Workaround: Seems this is a Juju bug that sends event.unit == None
            return

        if data := event.relation.data[event.unit].get("data"):
            self._stored.loki_push_api = json.loads(data)["loki_push_api"]

        event.relation.data[self._charm.app]["metadata"] = json.dumps(self._scrape_metadata)
        self._set_alert_rules(event)

    def _set_alert_rules(self, event):
        """Set alert rules into relation data.

        Args:
            event: a `CharmEvent` in response to which the consumer
                charm must update its relation data.
        """

        if alert_groups := self._labeled_alert_groups:
            event.relation.data[self._charm.app]["alert_rules"] = json.dumps(
                {"groups": alert_groups}
            )

    def _label_alert_topology(self, rule) -> dict:
        """Insert juju topology labels into an alert rule.

        Args:
            rule: a dictionary representing a Loki alert rule.

        Returns:
            a dictionary representing Loki alert rule with Juju
            topology labels.
        """
        metadata = self._scrape_metadata
        labels = rule.get("labels", {})
        labels["juju_model"] = metadata["model"]
        labels["juju_model_uuid"] = metadata["model_uuid"]
        labels["juju_application"] = metadata["application"]
        rule["labels"] = labels
        return rule

    def _label_alert_expression(self, rule) -> dict:
        """Insert juju topology filters into a Loki alert rule.

        Args:
            rule: a dictionary representing a Loki alert rule.

        Returns:
            a dictionary representing a Loki alert rule that filters based
            on juju topology.
        """
        metadata = self._scrape_metadata
        topology = 'juju_model="{}", juju_model_uuid="{}", juju_application="{}"'.format(
            metadata["model"], metadata["model_uuid"], metadata["application"]
        )
        expr = rule["expr"]
        expr = expr.replace("%%juju_topology%%", topology)
        rule["expr"] = expr
        return rule

    def _validate_alert_rule(self, rule: dict, rule_file):
        """This method validates if an alert rule is well formed

        Args:
            rule: A dictionary containing an alert rule definition
            rule_file: The rule_file name

        Returns:
            Raises an AlertRuleError exceprtion if the alert rule is not well formed
        """

        missing = ["alert", "expr"]

        for field in missing:
            if field not in rule.keys():
                message = (
                    f"Alert rule '{rule_file.name}' is not well formed. Field '{field}' is missing"
                )
                raise AlertRuleError(message)

        if rule["expr"].find("%%juju_topology%%") < 0:
            message = (
                f"Alert rule '{rule_file.name}' is not well formed. "
                + "%%juju_topology%% placeholder is not present"
            )
            raise AlertRuleError(message)

    @property
    def loki_push_api(self):
        """Fetch Loki Push API endpoint sent from LokiProvider throught relation data

        Returns:
            Loki Push API endpoint
        """
        return self._stored.loki_push_api

    @property
    def _labeled_alert_groups(self) -> list:
        """Load alert rules from rule files.

        All rules from files for a consumer charm are loaded into a single
        group. The generated name of this group includes Juju topology
        prefixes.

        Returns:
            a list of Loki alert rule groups.
        """
        alerts = []

        for path in Path(self._ALERT_RULES_PATH).glob("*.rule"):
            if not path.is_file():
                continue

            logger.debug("Reading alert rule from %s", path)
            with path.open() as rule_file:
                # Load a list of rules from file then add labels and filters
                try:
                    rule = yaml.safe_load(rule_file)
                    self._validate_alert_rule(rule, rule_file)
                    rule = self._label_alert_topology(rule)
                    rule = self._label_alert_expression(rule)
                    alerts.append(rule)
                except AlertRuleError as e:
                    self._charm.model.unit.status = BlockedStatus(str(e))
                except FileNotFoundError as e:
                    message = "Failed to read alert rules from %s: %s", path.name, str(e)
                    logger.error(message)
                    self._charm.model.unit.status = BlockedStatus(message)

        groups = []
        if alerts:
            metadata = self._scrape_metadata
            group = {
                "name": "{model}_{model_uuid}_{application}_alerts".format(**metadata),
                "rules": alerts,
            }
            groups.append(group)
        return groups

    @property
    def _scrape_metadata(self) -> dict:
        """Generate scrape metadata.

        Returns:
            Scrape configutation metadata for this logging provider charm.
        """
        metadata = {
            "model": f"{self._charm.model.name}",
            "model_uuid": f"{self._charm.model.uuid}",
            "application": f"{self._charm.model.app.name}",
        }
        return metadata
