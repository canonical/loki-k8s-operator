#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import json
import logging

from ops.framework import StoredState
from ops.relation import ProviderBase

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

    def __init__(self, charm, name: str, service: str, version: str):
        """A Loki service provider.

        Args:

            charm: a `CharmBase` instance that manages this
                instance of the Loki service.
            name: string name of the relation that provides the
                Loki monitoring service.
            service: string name of service provided. This is used by
                `LokiConsumer` to validate this service as
                acceptable. Hence the string name must match one of the
                acceptable service names in the `LokiConsumer`s
                `consumes` argument. Typically this string is just "loki".
            version: a string providing the semantic version of the Loki
                application being provided.
        """
        super().__init__(charm, name, service, version)
        self.charm = charm
        self._relation_name = name
        events = self.charm.on[name]
        self.framework.observe(events.relation_joined, self._on_loki_relation_joined)

    ##############################################
    #               RELATIONS                    #
    ##############################################
    def _on_loki_relation_joined(self, event):
        if not self.charm.unit.is_leader():
            return

        event.relation.data[self.charm.app]["data"] = self.relation_data

    ##############################################
    #               PROPERTIES                   #
    ##############################################
    @property
    def relation_data(self) -> str:
        """Fetch relation data

        Returns:
            relation data as json string"""

        data = {"loki_push_api": f"http://{self.charm.unit_ip}:3100/loki/api/v1/push"}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP"""
        if bind_address := self.charm.model.get_binding(self._relation_name).network.bind_address:
            return str(bind_address)
        return ""

