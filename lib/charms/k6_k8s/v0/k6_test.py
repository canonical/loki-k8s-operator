"""Charm library to transfer k6 tests.

Charms that need to push load tests to a k6 charm, should use the
`K6TestProvider` class. Charms that run those tests and need to receive them,
should use the `K6TestRequirer` class.
"""

import json
import logging
from typing import Dict, Optional
from cosl import JujuTopology
from ops import CharmBase, Object, Relation
from pathlib import Path
import os

LIBID = "notarealoneyet"
LIBAPI = 0
LIBPATCH = 1
PYDEPS = ["cosl"]

logger = logging.getLogger(__name__)

DEFAULT_REQUIRER_NAME = "receive-k6-tests"
DEFAULT_PROVIDER_NAME = "send-k6-tests"
RELATION_INTERFACE_NAME = "k6_tests"


class K6TestRequirer(Object):
    """Helper class for the 'receiving' side of k6 tests.

    The `K6TestRequirer` object can be instantiated as follows in your charm:

    ```
    def __init__(self, *args):
        ...
        self.k6_tests = K6TestRequirer(self)
        ...
    ```

    The `K6TestRequirer` assumes that, in your charm metadata, you declare a
    relation as follows:

    ```
    requires:
        receive-k6-tests:  # Relation name
            interface: k6_tests  # Relation interface
    ```
    """

    def __init__(self, charm: CharmBase, *, relation_name: str = DEFAULT_REQUIRER_NAME):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    @property
    def tests(self) -> Optional[Dict[str, Dict]]:
        """Get the k6 tests from all relations.

        Returns:
            A dictionary mapping the app name to the tests it provides.
        """
        tests = {}
        for relation in self.model.relations[self._relation_name]:
            app = relation.app
            if not app:
                continue
            data = json.loads(relation.data[app]["k6"])
            tests[app.name] = data.get("tests", {})
        return tests

    @property
    def environment(self) -> Optional[Dict[str, str]]:
        """Get the k6 tests from all relations.

        Returns:
            A dictionary mapping the app name to the tests it provides.
        """
        tests = {}
        for relation in self.model.relations[self._relation_name]:
            app = relation.app
            if not app:
                continue
            data = json.loads(relation.data[app]["k6"])
            tests[app] = data.get("environment", {})
        return tests


class K6TestProvider(Object):
    """Helper class for the 'sending' side of k6 tests.

    The `K6TestProvider` object can be instantiated as follows in your charm:

    ```
    def __init__(self, *args):
        ...
        environment: Dict[str, str] = {"SOME_ENDPOINT": "http://10.1.2.3:1234"}
        self.k6_tests = K6TestProvider(
            self,
            tests_folder="tests/load",
            environment=environment,
        )
        self.k6_tests.reconcile()
        ...
    ```

    The `K6TestProvider` assumes that, in your charm metadata, you declare a
    relation as follows:

    ```
    requires:
        send-k6-tests:  # Relation name
            interface: k6_tests  # Relation interface
    ```
    """

    def __init__(
        self,
        charm: CharmBase,
        *,
        relation_name: str = DEFAULT_PROVIDER_NAME,
        tests_path: str = "tests/load",
        environment: Optional[Dict[str, str]] = None,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._tests_path = tests_path
        self._k6_environment = environment

        self._topology: JujuTopology = JujuTopology.from_charm(charm)
        self.relation: Optional[Relation] = charm.model.get_relation(relation_name)

    @property
    def k6_tests(self) -> Optional[Dict[str, str]]:
        """Read the k6 tests from the folder specified in the constructor."""
        tests = {}
        # Walk through the directory
        for root, _, files in os.walk(self._tests_path):
            for filename in files:
                # Create the full file path
                file_path = os.path.join(root, filename)
                try:
                    # Open the file and read its contents
                    with open(file_path, "r", encoding="utf-8") as f:
                        contents = f.read()
                        tests[filename] = contents
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")
        return tests or None

    def _set_data(self):
        """Update relation data with the passed information.

        Example:
            {
                "tests": {
                    "script-one.js": "import { check, ...",
                    "script-two.js": ...,
                }
                "environment": {
                    "SOME_ENDPOINT": "http://some.url.local:12345"
                }
            }
        """
        if not self.relation:
            return
        data: Dict[str, Dict] = {
            "tests": self.k6_tests or {},
            "environment": self._k6_environment or {},
        }
        self.relation.data[self._charm.app]["k6"] = json.dumps(data)

    def reconcile(self):
        """Re-generate the world state for the charm library."""
        self._set_data()
