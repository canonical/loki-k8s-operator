#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import json
import logging
import os
from pathlib import Path

import yaml
from ops.charm import CharmBase
from ops.framework import Object, StoredState

# The unique Charmhub library identifier, never change it
LIBID = "bf76f23cdd03464b877c52bd1d2f563e"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3

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


class LokiProvider(RelationManagerBase):
    """
    LokiProvider class
    """

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
        self.container = self.charm.unit.get_container(self.charm.model.name)
        events = self.charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)
        self.framework.observe(events.relation_departed, self._on_logging_relation_departed)

    def _on_logging_relation_changed(self, event):
        """IMPROVE DOCSTRING"""

        if event.relation.data[self.charm.unit].get("data") is None:
            event.relation.data[self.charm.unit]["data"] = self._loki_push_api
            logger.debug("Saving Loki url in relation data %s", self._loki_push_api)

        if event.relation.data.get(event.relation.app) is not None:
            logger.warning("Saving alerts on disk")
            self._remove_alert_rules_files(self.container)
            self._generate_alert_rules_files(self.container)

    def _on_logging_relation_departed(self, event):
        """IMPROVE DOCSTRING"""
        if event.relation.data.get(event.relation.app) is not None:
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
        """Remove alert rules files"""

        for f in container.list_files(RULES_DIR):
            container.remove_path(f.path, recursive=True)
            logger.debug("Alert rule file '%s' deleted", f.path)

    def _generate_alert_rules_files(self, container) -> None:
        """Generate and upload alert rules files"""
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
        logger.warning("-" * 30)
        logger.warning(event.unit)

        if event.unit is None:
            # Workaround: Seems this is a Juju bug that sends event.unit == None
            return

        # Get loki_push_api url from relation data
        if data := event.relation.data[event.unit].get("data"):
            self._stored.loki_push_api = json.loads(data)["loki_push_api"]

        event.relation.data[self._charm.app]["metadata"] = json.dumps(self._scrape_metadata)
        self._set_alert_rules(event)

    def _set_alert_rules(self, event):
        event.relation.data[self._charm.unit]["loki_host"] = str(
            self._charm.model.get_binding(event.relation).network.bind_address
        )

        if not self._charm.unit.is_leader():
            return

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

        if expr := rule.get("expr", None):
            expr = expr.replace("%%juju_topology%%", topology)
            rule["expr"] = expr
        else:
            logger.error("Invalid alert expression in %s", rule.get("alert"))

        return rule

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
        logger.warning(self._ALERT_RULES_PATH)
        for path in Path(self._ALERT_RULES_PATH).glob("*.rule"):
            if not path.is_file():
                continue

            logger.debug("Reading alert rule from %s", path)
            with path.open() as rule_file:
                # Load a list of rules from file then add labels and filters
                try:
                    rule = yaml.safe_load(rule_file)
                    rule = self._label_alert_topology(rule)
                    rule = self._label_alert_expression(rule)
                    alerts.append(rule)
                except Exception as e:
                    logger.error("Failed to read alert rules from %s: %s", path.name, str(e))

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
