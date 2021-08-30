# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from typing import Dict
from unittest.mock import PropertyMock, patch

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import LokiOperatorCharm


class PushPullMock:
    def __init__(self):
        self._filesystem: Dict[str, str] = {}

    def pull(self, path: str, *args, **kwargs) -> str:
        return self._filesystem.get(path, "")

    def push(self, path: str, source: str, *args, **kwargs) -> None:
        self._filesystem[path] = source

    def patch_push(self):
        return patch("ops.testing._TestingPebbleClient.push", self.push)

    def patch_pull(self):
        return patch("ops.testing._TestingPebbleClient.pull", self.pull)


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name: str = "loki"
        self.push_pull_mock = PushPullMock()
        self.harness = Harness(LokiOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    def test_pebble_layer_added(self):
        with self.push_pull_mock.patch_push(), self.push_pull_mock.patch_pull():
            self.harness.container_pebble_ready(self.container_name)
        plan = self.harness.get_container_pebble_plan(self.container_name).to_dict()

        # Check we've got the plan as expected
        self.assertIsNotNone(services := plan.get("services"))
        self.assertIsNotNone(loki := services.get("loki"))
        self.assertIsNotNone(command := loki.get("command"))

        # Check command contains key arguments
        self.assertIn("/usr/bin/loki", command)
        self.assertIn("-target", command)
        self.assertIn("-config.file", command)

        # Check the service was started
        service = self.harness.model.unit.get_container("loki").get_service("loki")
        self.assertTrue(service.is_running())

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    @patch("loki_server.LokiServer.is_ready", new_callable=PropertyMock)
    def test__provide_loki(self, mock_is_ready, mock_version):
        mock_is_ready.return_value = True
        mock_version.return_value = "2.3.0"
        self.assertEqual(type(self.harness.charm.unit.status), ActiveStatus)
