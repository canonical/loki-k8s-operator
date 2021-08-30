#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import logging

import requests

logger = logging.getLogger(__name__)


class LokiServer:
    """Class to manage Loki server"""

    def __init__(self, host="localhost", port=3100, timeout=2.0):
        """Utility to manage a Loki application.
        Args:
            host: host address of Loki application.
            port: port on which Loki service is exposed.
            timeout: timeout for the http request
        """
        self.host = host
        self.port = port
        self.timeout = timeout

    def _build_info(self):
        """Fetch build information from Loki.

        Returns:
            a dictionary containing build information (for instance
            version) of the Loki application. If the Loki
            instance is not reachable then an empty dictionary is
            returned.
        """
        api_path = "loki/api/v1/status/buildinfo"
        url = f"http://{self.host}:{self.port}/{api_path}"

        try:
            response = requests.get(url, timeout=self.timeout)
            info = response.json()

            if response.status_code == requests.codes.ok:
                return info
        except Exception:
            # Nothing worth logging, seriously
            pass

        return {}

    @property
    def version(self) -> str:
        """Fetch Loki version.

        Returns:
            a string consisting of the Loki version information or
            an empty string if Loki server is not reachable.
        """

        # Un-comment the following return once new Loki 2.3.1 version is released.
        #
        # We are hardcoding version here because there is and bug in last stable Loki version
        # (2.3.0) that do not return its version: https://github.com/grafana/loki/issues/4133
        # This bug it was already addressed in PR: https://github.com/grafana/loki/pull/4135
        # but it's note released yet.
        return "2.3.1"

        info = self._build_info()

        if info:
            return info.get("version", None)
        return ""

    @property
    def loki_push_api(self) -> str:
        return f"http://{self.host}:{self.port}/loki/api/v1/push"

    @property
    def is_ready(self) -> bool:
        """Loki is up and running if we can get its version"""
        return True if self.version != "" else False
