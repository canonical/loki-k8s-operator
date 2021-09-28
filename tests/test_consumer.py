# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
import json

from charms.loki_k8s.v0.loki import LokiConsumer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness


class FakeConsumerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self.loki_consumer = LokiConsumer(self, "logging")

    @property
    def _loki_push_api(self) -> str:
        loki_push_api = f"http://{self.unit_ip}:{self.charm._port}/loki/api/v1/push"
        data = {"loki_push_api": loki_push_api}
        return json.dumps(data)

    @property
    def unit_ip(self) -> str:
        """Returns unit's IP"""
        return "10.1.2.3"


class TestLokiConsumer(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeConsumerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test__on_logging_relation_changed_no_leader(self):
        self.harness.set_leader(False)
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.assertEqual(self.harness.update_relation_data(rel_id, "promtail/0", {}), None)

    def test__on_logging_relation_changed_no_unit(self):
        rel_id = self.harness.add_relation("logging", "promtail")
        self.assertEqual(self.harness.update_relation_data(rel_id, "promtail", {}), None)

    def test__on_logging_relation_changed(self):
        self.harness.set_leader(True)
        rel_id = self.harness.add_relation("logging", "promtail")
        self.harness.add_relation_unit(rel_id, "promtail/0")
        self.harness.update_relation_data(
            rel_id,
            "promtail/0",
            {"data": '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'},
        )
