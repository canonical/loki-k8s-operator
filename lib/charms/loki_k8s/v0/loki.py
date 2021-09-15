#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import json
import logging

from ops.charm import CharmBase
from ops.framework import Object, StoredState

# The unique Charmhub library identifier, never change it
LIBID = "bf76f23cdd03464b877c52bd1d2f563e"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3

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

        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP"""
        if bind_address := self.charm.model.get_binding(self._relation_name).network.bind_address:
            return str(bind_address)
        return ""


class LokiConsumer(RelationManagerBase):
    """
    Loki Consumer class
    """

    _stored = StoredState()

    def __init__(self, charm: CharmBase, relation_name: str):
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
        """
        super().__init__(charm, relation_name)
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
