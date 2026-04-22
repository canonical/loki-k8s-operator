# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import textwrap
import unittest

from charms.loki_k8s.v1.loki_push_api import LogForwarder, _PebbleLogClient
from ops.charm import CharmBase
from ops.testing import Harness


class FakeCharm(CharmBase):
    """Container charm for forwarding logs using the logforwarder class."""

    metadata_yaml = textwrap.dedent(
        """
        containers:
          consumer:
            resource: consumer-image

        requires:
          logging:
            interface: loki_push_api
        """
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.log_forwarder = LogForwarder(self)


class TestLogForwarding(unittest.TestCase):
    """Test that the Log Forwarder implementation works."""

    def setUp(self):
        self.harness = Harness(FakeCharm, meta=FakeCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()

    def test_handle_logging_with_relation_lifecycle(self):
        rel_id = self.harness.add_relation("logging", "loki")
        for i in range(2):
            loki_unit = f"loki/{i}"
            endpoint = f"http://loki-{i}:3100/loki/api/v1/push"
            data = json.dumps({"url": f"{endpoint}"})
            self.harness.add_relation_unit(rel_id, loki_unit)
            self.harness.set_planned_units(1)
            self.harness.update_relation_data(
                rel_id,
                loki_unit,
                {"endpoint": data},
            )
        relation_obj = self.harness.model.relations["logging"][0]
        expected_endpoints = {
            "loki/0": "http://loki-0:3100/loki/api/v1/push",
            "loki/1": "http://loki-1:3100/loki/api/v1/push",
        }
        self.assertDictEqual(
            self.harness.charm.log_forwarder._fetch_endpoints(relation_obj), expected_endpoints
        )
        expected_layer_config = {
            "loki/0": {
                "override": "replace",
                "type": "loki",
                "location": "http://loki-0:3100/loki/api/v1/push",
                "services": ["all"],
                "labels": {
                    "product": "Juju",
                    "charm": self.harness.charm.log_forwarder.topology._charm_name,
                    "juju_model": self.harness.charm.log_forwarder.topology._model,
                    "juju_model_uuid": self.harness.charm.log_forwarder.topology._model_uuid,
                    "juju_application": self.harness.charm.log_forwarder.topology._application,
                    "juju_unit": self.harness.charm.log_forwarder.topology._unit,
                },
            },
            "loki/1": {
                "override": "replace",
                "type": "loki",
                "location": "http://loki-1:3100/loki/api/v1/push",
                "services": ["all"],
                "labels": {
                    "product": "Juju",
                    "charm": self.harness.charm.log_forwarder.topology._charm_name,
                    "juju_model": self.harness.charm.log_forwarder.topology._model,
                    "juju_model_uuid": self.harness.charm.log_forwarder.topology._model_uuid,
                    "juju_application": self.harness.charm.log_forwarder.topology._application,
                    "juju_unit": self.harness.charm.log_forwarder.topology._unit,
                },
            },
        }
        actual_layer_config = _PebbleLogClient._build_log_targets(
            expected_endpoints, self.harness.charm.log_forwarder.topology, True
        )
        self.assertDictEqual(expected_layer_config, actual_layer_config)
