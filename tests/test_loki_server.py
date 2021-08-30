# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import unittest
from unittest.mock import PropertyMock, patch

from loki_server import LokiServer


def mocked_requests_get_ok(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    response = {
        "version": "2.3.1",
        "revision": "668622c81",
        "branch": "k59",
        "buildUser": "root@486a284bafb4",
        "buildDate": "2021-08-25T19:04:36Z",
        "goVersion": "",
    }
    return MockResponse(response, 200)


def mocked_requests_get_empty(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    return MockResponse({}, 200)


def mocked_requests_get_exception(*args, **kwargs):
    raise Exception("Some error")


class TestLokiServer(unittest.TestCase):
    @patch("loki_server.LokiServer._build_info")
    def test__version(self, mock_build_info):
        server = LokiServer()
        server_info = '{"version":"2.3.1","revision":"668622c81","branch":"k59","buildUser":"root@486a284bafb4","buildDate":"2021-08-25T19:04:36Z","goVersion":""}'
        mock_build_info.return_value = json.loads(server_info)

        expected_version = "2.3.0"
        self.assertEqual(server.version, expected_version)

        non_expected_version = "2.3.3"
        self.assertNotEqual(server.version, non_expected_version)

    def test_loki_push_api(self):
        server_1 = LokiServer(host="10.1.2.3", port=3100)
        expected_api_1 = "http://10.1.2.3:3100/loki/api/v1/push"
        self.assertEqual(server_1.loki_push_api, expected_api_1)

        server_2 = LokiServer()
        expected_api_2 = "http://localhost:3100/loki/api/v1/push"
        self.assertEqual(server_2.loki_push_api, expected_api_2)

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test_is_ready_true(self, mock_version):
        mock_version.return_value = "2.3.1"
        server = LokiServer()
        self.assertTrue(server.is_ready)

    @patch("loki_server.LokiServer.version", new_callable=PropertyMock)
    def test_is_ready_false(self, mock_version):
        mock_version.return_value = ""
        server = LokiServer()
        self.assertFalse(server.is_ready)

    @patch("requests.get", side_effect=mocked_requests_get_ok)
    def test__build_info_ok(self, mock_get):
        server = LokiServer()
        json_data = server._build_info()
        expected_data = {
            "version": "2.3.1",
            "revision": "668622c81",
            "branch": "k59",
            "buildUser": "root@486a284bafb4",
            "buildDate": "2021-08-25T19:04:36Z",
            "goVersion": "",
        }
        self.assertDictEqual(expected_data, json_data)

    @patch("requests.get", side_effect=mocked_requests_get_empty)
    def test__build_info_error(self, mock_get):
        server = LokiServer()
        json_data = server._build_info()
        self.assertDictEqual({}, json_data)

    @patch("requests.get", side_effect=mocked_requests_get_exception)
    def test__build_info_exception(self, mock_get):
        server = LokiServer()
        json_data = server._build_info()
        self.assertDictEqual({}, json_data)
