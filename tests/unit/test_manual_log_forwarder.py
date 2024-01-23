# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import textwrap
import unittest
from typing import Dict

from charms.loki_k8s.v1.loki_push_api import ManualLogForwarder
from ops import Relation
from ops.charm import CharmBase
from ops.testing import Harness


class FakeCharm(CharmBase):
    """Container charm for forwarding logs using the ManualLogForwarder class."""

    metadata_yaml = textwrap.dedent(
        """
        containers:
          consumer:
            resource: consumer-image

        requires:
          diff-rel:
            interface: diff-int
        """
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.log_forwarder = ManualLogForwarder(
            charm=self,
            relation_name="diff-rel",
            loki_endpoints=self._extract_urls(self.get_rel_obj()),
        )

    def get_rel_obj(self):
        return self.model.relations.get("diff-rel")[0]

    def _extract_urls(self, relation: Relation) -> Dict[str, str]:
        """Default getter function to extract Loki endpoints from a relation.

        Returns:
            A dictionary of remote units and the respective Loki endpoint.
            {
                "loki/0": "http://loki1:3100/loki/api/v1/push",
                "another-loki/0": "http://loki2:3100/loki/api/v1/push",
            }
        """
        endpoints: Dict = {}

        for unit in relation.units:
            endpoint = relation.data[unit]["endpoint"]
            deserialized_endpoint = json.loads(endpoint)
            url = deserialized_endpoint["url"]
            endpoints[unit.name] = url

        return endpoints


class TestLogForwarding(unittest.TestCase):
    """Test that the Log Forwarder implementation works."""

    def setUp(self):
        self.harness = Harness(FakeCharm, meta=FakeCharm.metadata_yaml)
        rel_id = self.harness.add_relation("diff-rel", "anycharm")
        for i in range(2):
            loki_unit = f"anycharm/{i}"
            endpoint = f"http://loki-{i}:3100/loki/api/v1/push"
            data = json.dumps({"url": f"{endpoint}"})
            self.harness.add_relation_unit(rel_id, loki_unit)
            self.harness.set_planned_units(1)
            self.harness.update_relation_data(
                rel_id,
                loki_unit,
                {"endpoint": data},
            )
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()

    def test_handle_logging_with_relation_lifecycle(self):
        expected_endpoints = {
            "anycharm/0": "http://loki-0:3100/loki/api/v1/push",
            "anycharm/1": "http://loki-1:3100/loki/api/v1/push",
        }
        self.assertEqual(self.harness._charm.log_forwarder._loki_endpoints, expected_endpoints)
