#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Integration tester charm for Loki Operator."""

import logging
from multiprocessing import Queue

import logging_loki  # type: ignore
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer
from charms.observability_libs.v0.juju_topology import JujuTopology
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

        self.topology = JujuTopology.from_charm(self)
        self.unit.status = ActiveStatus()

    def _setup_logging(self, handlers_init: dict = None) -> None:
        """Ensure logging is configured correctly.

        A dict of "wanted" loggers is passed in, and the list of current loggers known to
        `logging.getLogger()` is compared. If the "wanted" loggers are not part of that list,
        or that list has loggers which are not "wanted", it is reconciled via `addHandler()` and
        `removeHandler()`. Python's `logging` objects are actually global variables, and this
        add/remove is a necessary step to ensure the state is "correct" rather than blindly
        adding/removing them.

        Args:
            handlers_init: a dict of 'name' -> handler objects
        """
        handlers_init = handlers_init or {}
        logger = logging.getLogger("loki-tester")

        # Make sure we always have a local console logger
        console_handler = {"console": {"handler": logging.StreamHandler(), "level": logging.INFO}}
        handlers_init.update(console_handler)

        for k, v in handlers_init.items():
            # Give each handler a "name" property which matches so we can find it
            v["handler"].name = k
            v["handler"].setLevel(v["level"])

        handlers = {v["handler"].name: v["handler"] for v in handlers_init.values()}

        # Check against logger.Manager and exclude "useless" values like logging.Placeholder
        existing_handlers: dict[str, logging.Handler] = {k: v for k, v in logger.manager.loggerDict.items() if not isinstance(v, logging.PlaceHolder) and "loki" not in k}  # type: ignore

        if set(handlers.keys()) == set(existing_handlers.keys()):
            # Nothing to do
            return

        # If we're here, we need to add or remove some loggers
        to_remove = [v for k, v in existing_handlers.items() if k not in handlers]
        to_add = [v for k, v in handlers.items() if k not in existing_handlers]

        # Remove loggers we don't want anymore
        for h in to_remove:
            logger.removeHandler(h)

        # Add any missing loggers whichshould be there
        for h in to_add:
            logger.addHandler(h)

        self.logger = logger
        self.logger.debug(
            "Configured logging with {} handlers: {}".format(
                len(handlers.keys()), ", ".join(handlers.keys())
            )
        )

    def _on_config_changed(self, _):
        """Handle changed configuration."""
        self.set_logger()
        self.log("debug", "Handling configuration change")

    def _on_update_status(self, _):
        """Handle status updates."""
        self.set_logger()
        self.log("debug", "Updating status")

    def _on_loki_push_api_endpoint_joined(self, _):
        self.set_logger()
        self.log("debug", "Loki push API endpoint joined")

    def _on_loki_push_api_endpoint_departed(self, _):
        self.set_logger()
        self.log("debug", "Loki push API endpoint departed")

    def _on_log_error_action(self, event):
        self.set_logger()
        message = event.params["message"]
        logged = self.log("error", message)
        if logged:
            self.logger.warning("Error message logged!")
            event.set_results({"message": "Error message successfully logged"})
        else:
            self.logger.warning("Error message not logged!")
            event.fail("Failed to log error message")

    def set_logger(self, local_only=False):
        """Set self.log to a meaningful value.

        Set the log attribute for this charm. There is a `local_only` param which
        can be used on RelationBroken or RelationDeparted where leaving a "remote"
        Loki logger may lead to attempts to send a request to a dying endpoint,
        and `local_only` will ensure that it is only to the console of this charm
        to isolate behavior.

        If `local_only` is not set, try to fetch a list of Loki endpoints and set
        the logger for this charm to match. If the endpoint list is empty, then
        it will be console only.

        Args:
            local_only: a boolean to enable only local console logging
        """
        if local_only:
            self._setup_logging({})
            return

        tags = self.topology.label_matcher_dict
        log_endpoints = self._loki_consumer.loki_endpoints

        loki_handlers = {}
        for idx, endpoint in enumerate(log_endpoints):
            logging_loki.emitter.LokiEmitter.level_tag = "level"
            loki_handlers.update(
                {
                    "loki-{}".format(idx): {
                        "handler": logging_loki.LokiQueueHandler(
                            Queue(-1), url=endpoint["url"], version="1", tags=dict(tags)
                        ),
                        "level": logging.DEBUG,
                    }
                }
            )

        self._setup_logging(loki_handlers)

        if loki_handlers:
            self.log("debug", "Successfully set Loki Logger")

    def log(self, level, msg):
        try:
            getattr(self.logger, level)(msg)
            return True
        except AttributeError:
            return False


if __name__ == "__main__":
    main(LokiTesterCharm)
