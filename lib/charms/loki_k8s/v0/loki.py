#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import json
import logging

from ops.relation import ConsumerBase, ProviderBase

# The unique Charmhub library identifier, never change it
LIBID = "Qwerty"  # TODO: get LIBID from charmhub

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

logger = logging.getLogger(__name__)


class LokiProvider(ProviderBase):
    """
    LokiProvider class
    """

    def __init__(self, charm, relation_name: str, service: str, version: str):
        """A Loki service provider.

        Args:

            charm: a `CharmBase` instance that manages this
                instance of the Loki service.
            relation_name: string name of the relation that provides the
                Loki logging service.
            service: string name of service provided. This is used by
                `LokiConsumer` to validate this service as
                acceptable. Hence the string name must match one of the
                acceptable service names in the `LokiConsumer`s
                `consumes` argument. Typically this string is just "loki".
            version: a string providing the semantic version of the Loki
                application being provided.
        """
        super().__init__(charm, relation_name, service, version)
        self.charm = charm
        self._relation_name = relation_name
        events = self.charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_logging_relation_changed)

    ##############################################
    #               RELATIONS                    #
    ##############################################
    def _on_logging_relation_changed(self, event):
        """Anytime there are changes in relations between Loki
        provider and consumer charms the Loki charm is informed,
        through a `RelationChanged` event.
        The Loki charm then updates relation data with the Loki Push API url.
        """
        event.relation.data[self.charm.unit]["data"] = self._loki_push_api
        logger.debug("Saving Loki url in relation data %s", self._loki_push_api)

    ##############################################
    #               PROPERTIES                   #
    ##############################################
    @property
    def _loki_push_api(self) -> str:
        """Fetch Loki push API URL

        Returns:
            Loki push API URL as json string"""

        loki_push_api = f"http://{self.unit_ip}:{self.charm.port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP"""
        if bind_address := self.charm.model.get_binding(self._relation_name).network.bind_address:
            return str(bind_address)
        return ""


class LokiConsumer(ConsumerBase):
    """
    Loki Consumer class
    """

    def __init__(self, charm, relation_name: str, consumes: dict, multi: bool = False):
        """Construct a Loki charm client.

        The `LokiConsumer` object provides configurations to a Loki client charm.
        A charm instantiating this object needs Loki information, for instance the
        Loki API endpoint to push logs.
        The `LokiConsumer` can be instantiated as follows:

            self.loki_lib = LokiConsumer(self, "logging", consumes={"loki": ">=2.3.0"})

        Args:

            charm: a `CharmBase` object that manages this
                `LokiConsumer` object. Typically this is
                `self` in the instantiating class.
            relation_ name: a string name of the relation between `charm` and
                the Loki charmed service.
            consumes: a dictionary of acceptable logging service
                providers. The keys of the dictionary are string names
                of logging service providers. For loki, this
                is typically "loki". The values of the
                dictionary are corresponding minimal acceptable
                semantic version specfications for the logging
                service.
        """
        super().__init__(charm, relation_name, consumes, multi)
        self._stored.set_default(loki_push_api=None)
        self._charm = charm
        self._relation_name = relation_name
        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_logging_relaton_changed)

    def _on_logging_relaton_changed(self, event):
        if event.unit is None:
            # Workaround: Seems this is a Juju bug that sends event.unit == None
            return

        if data := event.relation.data[event.unit].get("data"):
            self._stored.loki_push_api = json.loads(data)["loki_push_api"]

    @property
    def loki_push_api(self):
        """Fetch Loki Push API endpoint sent from LokiProvider throught relation data

        Returns:
            Loki Push API endpoint
        """
        return self._stored.loki_push_api
