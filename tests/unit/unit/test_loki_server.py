# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import threading
import unittest
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from unittest.mock import patch

import requests

from loki_server import LokiServer


def mocked_requests_get_empty(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    return MockResponse({}, 200)


def mocked_requests_get_exception(*args, **kwargs):
    raise requests.exceptions.HTTPError("404")


class ThreadWithStop(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(ThreadWithStop, self).__init__(*args, **kwargs)
        self.stop = threading.Event()

    def run(self):
        while True:
            self.stop.wait()


class FakeLokiRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):  # noqa: N802
        json_response = json.dumps(
            {
                "version": "2.4.1",
                "revision": "668622c81",
                "branch": "k59",
                "buildUser": "root@486a284bafb4",
                "buildDate": "2021-08-25T19:04:36Z",
                "goVersion": "",
            }
        )
        self.send_response(200)
        self.send_header("Content-type", "application/json;charset=utf-8")
        self.send_header("Content-length", str(len(json_response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json_response.encode("utf-8"))
        self.wfile.flush()


class FakeLokiServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    logging = False


class TestLokiServer(unittest.TestCase):
    def setUp(self):
        self.fake_loki = FakeLokiServer(("127.0.0.1", 3100), FakeLokiRequestHandler)
        self.fake_loki_thread = threading.Thread(target=self.fake_loki.serve_forever)
        self.fake_loki_thread.setDaemon(True)
        if not self.fake_loki_thread.is_alive():
            self.fake_loki_thread.start()

    def tearDown(self):
        self.fake_loki.shutdown()
        self.fake_loki.server_close()
        self.fake_loki_thread.join()

    @patch("loki_server.LokiServer._build_info")
    def test__version(self, mock_build_info):
        server = LokiServer()
        server_info = '{"version":"2.4.1","revision":"668622c81","branch":"k59","buildUser":"root@486a284bafb4","buildDate":"2021-08-25T19:04:36Z","goVersion":""}'
        mock_build_info.return_value = json.loads(server_info)

        expected_version = "2.4.1"
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

    def test__build_info_ok(self):
        server = LokiServer()
        json_data = server._build_info()
        expected_data = {
            "version": "2.4.1",
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
        with self.assertRaises(requests.exceptions.HTTPError) as context:
            LokiServer()._build_info()

        self.assertTrue("404" in str(context.exception))

    def test__build_info_no_logs(self):
        # assertNoLogs is not present until 3.10, sooo....
        with self.assertRaises(AssertionError) as e, self.assertLogs(level="DEBUG"):
            server = LokiServer()
            json_data = server._build_info()
            expected_data = {
                "version": "2.4.1",
                "revision": "668622c81",
                "branch": "k59",
                "buildUser": "root@486a284bafb4",
                "buildDate": "2021-08-25T19:04:36Z",
                "goVersion": "",
            }
            self.assertDictEqual(expected_data, json_data)
        self.assertEqual("no logs of level DEBUG or higher triggered on root", str(e.exception))
