import logging
import requests

logger = logging.getLogger(__name__)
API_PATH = "loki/api/v1/status/buildinfo"


class LokiServer:
    """Class to manage Loki server"""

    def __init__(self, host="localhost", port="3100"):
        """Utility to manage a Loki application.
        Args:
            host: host address of Loki application.
            port: port on which Loki service is exposed.
        """
        self.host = host
        self.port = port

    def _build_info(self):
        """Fetch build information from Loki.

        Returns:
            a dictionary containing build information (for instance
            version) of the Loki application. If the Loki
            instance is not reachable then an empty dictionary is
            returned.
        """
        url = f"http://{self.host}:{self.port}/{API_PATH}"

        try:
            response = requests.get(url)
            info = response.json()

            if response.status_code == requests.codes.ok:
                return info
        except Exception:
            # Nothing worth logging, seriously
            pass

        return {}

    @property
    def version(self):
        """Fetch Loki version.

        Returns:
            a string consisting of the Loki version information or
            None if Loki server is not reachable.
        """
        info = self._build_info()
        if info:
            return info.get("version", None)
        return None
