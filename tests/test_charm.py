# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

from charm import LokiOperatorCharm
from ops.model import ActiveStatus
from ops.testing import Harness
from unittest.mock import patch, PropertyMock


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test__provide_loki(self, mock_version):
        mock_version.return_value = "2.3.1"
        self.harness.charm._provide_loki()
        self.assertEqual(type(self.harness.charm.unit.status), ActiveStatus)
