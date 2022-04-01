#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Integration tester charm for Loki Operator."""

import logging

import logging_loki  # type: ignore
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer, ProviderTopology
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus


class LokiTesterCharm(CharmBase):
    """A Loki Operator Client Charm."""

    def __init__(self, *args):
        super().__init__(*args)

        self._loki_consumer = LokiPushApiConsumer(self)

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.log_error_action, self._on_log_error_action)
        self.framework.observe(
            self._loki_consumer.on.loki_push_api_endpoint_joined,
            self._on_loki_push_api_endpoint_joined,
        )
        self.framework.observe(
            self._loki_consumer.on.loki_push_api_endpoint_departed,
            self._on_loki_push_api_endpoint_departed,
        )

        self.topology = ProviderTopology.from_charm(self)

        self.logger = None
        self.log_handler = None
        self.log_endpoints = []
        self.set_logger()

        self.log("debug", "Constructed loki tester")

    def _on_config_changed(self, _):
        """Handle changed configuration."""
        self.log("debug", "Handling configuration change")
        self.unit.status = ActiveStatus()

    def _on_update_status(self, _):
        self.log("debug", "Updating logger status")
        self.unit.status = ActiveStatus()

    def _on_loki_push_api_endpoint_joined(self, _):
        self.log("debug", "Loki push API endpoint joined")
        self.set_logger()

    def _on_loki_push_api_endpoint_departed(self, _):
        self.log("debug", "Loki push API endpoint departed")
        # TODO (multi-logger): remove only the logger whoe's endpoint departed
        self.logger = None

    def _on_log_error_action(self, event):
        message = event.params["message"]
        logged = self.log("error", message)
        if logged:
            event.set_results({"message": "Error message successfully logged"})
        else:
            event.fail("Failed to log error message")

    def set_logger(self):
        tags = self.topology.as_promql_label_dict()
        log_endpoints = self._loki_consumer.loki_endpoints

        if log_endpoints:
            logging_loki.emitter.LokiEmitter.level_tag = "level"
            # TODO (multi-logger): create logggers for each endpoint
            self.log_handler = logging_loki.LokiHandler(
                url=log_endpoints[0]["url"], version="1", tags=dict(tags)
            )
            # TODO (multi-logger): each logger will need a different name
            self.logger = logging.getLogger("Loki-Tester")
            self.logger.addHandler(self.log_handler)

            self.log("debug", "Successfully set Loki Logger")

    def log(self, level, msg):
        try:
            getattr(self.logger, level)(msg)
            return True
        except AttributeError:
            return False


if __name__ == "__main__":
    main(LokiTesterCharm)
