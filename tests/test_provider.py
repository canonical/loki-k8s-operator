# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, patch

from charms.loki_k8s.v0.loki import LokiProvider
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.testing import Harness


class FakeLokiCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._stored.set_default(num_events=0)
        self.port = 3100


class TestLokiProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FakeLokiCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    @patch("charms.loki_k8s.v0.loki.LokiProvider.unit_ip", new_callable=PropertyMock)
    def test_relation_data(self, mock_unit_ip):
        mock_unit_ip.return_value = "10.1.2.3"
        version = "2.3.1"
        provider = LokiProvider(self.harness.charm, "logging", "loki", version)
        expected_value = '{"loki_push_api": "http://10.1.2.3:3100/loki/api/v1/push"}'
        self.assertEqual(expected_value, provider.relation_data)
