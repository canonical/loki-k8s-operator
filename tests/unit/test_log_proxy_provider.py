# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap
import unittest
from unittest.mock import PropertyMock, patch

from charms.loki_k8s.v0.log_proxy import LogProxyProvider
from ops.charm import CharmBase
from ops.testing import Harness


class ProviderCharm(CharmBase):
    metadata_yaml = textwrap.dedent(
        """
        name: loki-k8s
        requires:
          log_proxy:
            interface: loki_push_api
            optional: true
        """
    )
    _http_listen_port = 3500
    _grpc_listen_port = 3600

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._log_proxy = LogProxyProvider(self)


class TestLogProxyProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(ProviderCharm, meta=ProviderCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
        self.harness.begin()

    @patch("charms.loki_k8s.v0.log_proxy.LogProxyProvider.unit_ip", new_callable=PropertyMock)
    def test__loki_push_api(self, mock_unit_ip: PropertyMock):
        mock_unit_ip.return_value = "10.1.2.3"
        expected = '{"loki_push_api": "http://10.1.2.3:3500/loki/api/v1/push"}'
        self.assertEqual(self.harness.charm._log_proxy._loki_push_api, expected)

    def test__promtail_binary_url(self):
        expected = '{"promtail_binary_zip_url": "https://github.com/grafana/loki/releases/download/v2.4.1/promtail-linux-amd64.zip"}'
        self.assertEqual(self.harness.charm._log_proxy._promtail_binary_url, expected)
