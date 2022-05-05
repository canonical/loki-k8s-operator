#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Helper for interacting with Loki throughout the charm's lifecycle."""


import logging

import requests

logger = logging.getLogger(__name__)

# Squash annoying debug logs from requests and urllib
logging.getLogger("urllib3").setLevel(logging.CRITICAL)


class LokiServerError(Exception):
    """Custom exception to indicate Loki server is not."""


class LokiServerNotReadyError(Exception):
    """Custom exception to indicate Loki server is not yet ready."""


class LokiServer:
    """Class to manage Loki server."""

    def __init__(self, host="localhost", port=3100, timeout=2.0):
        """Utility to manage a Loki application.

        Args:
            host: host address of Loki application.
            port: port on which Loki service is exposed.
            timeout: timeout for the http request
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{self.host}:{self.port}"
        self.timeout = timeout

    def _build_info(self):
        """Fetch build information from Loki.

        Returns:
            a dictionary containing build information (for instance
            version) of the Loki application. If the Loki
            instance is not reachable then a HTTPError exception is raised.
        """
        url = f"{self.base_url}/loki/api/v1/status/buildinfo"

        response = requests.get(url, timeout=self.timeout)

        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            response.raise_for_status()

    @property
    def version(self) -> str:
        """Fetch Loki version.

        Returns:
            a string consisting of the Loki version information.
            If Loki instance is not reachable then a LokiServerError
            exception is raised
        """
        try:
            info = self._build_info()
            version = info.get("version", None)
            if not version:
                raise LokiServerNotReadyError("Loki version could not be retrieved.")
            return version
        except requests.exceptions.ConnectionError as e:
            raise LokiServerNotReadyError(str(e))
        except requests.exceptions.HTTPError as e:
            raise LokiServerError(str(e))
        except requests.exceptions.RequestException as e:
            raise LokiServerError(str(e))

    @property
    def loki_push_api(self) -> str:
        """Fetch Loki PUSH API endpoint.

        Returns:
            a string consisting of the Loki Push API ndpoint
        """
        return f"{self.base_url}/loki/api/v1/push"
