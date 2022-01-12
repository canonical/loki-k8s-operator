# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import urllib.request

from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


async def get_unit_address(ops_test, app_name: str, unit_num: int) -> str:
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def is_loki_up(ops_test, app_name) -> bool:
    address = await get_unit_address(ops_test, app_name, 0)
    url = f"http://{address}:3100"
    logger.info("Loki public address: %s", url)

    response = urllib.request.urlopen(
        f"{url}/loki/api/v1/status/buildinfo", data=None, timeout=2.0
    )
    return response.code == 200 and "version" in json.loads(response.read())


class IPAddressWorkaround:
    """Context manager for deploying a charm that needs to have its IP address.

    Due to a juju bug, occasionally some charms finish a startup sequence without
    having an ip address returned by `bind_address`.
    https://bugs.launchpad.net/juju/+bug/1929364

    On entry, the context manager changes the update status interval to the minimum 10s, so that
    the update_status hook is trigger shortly.
    On exit, the context manager restores the interval to its previous value.
    """

    def __init__(self, ops_test: OpsTest):
        self.ops_test = ops_test

    async def __aenter__(self):
        """On entry, the update status interval is set to the minimum 10s."""
        config = await self.ops_test.model.get_config()
        self.revert_to = config["update-status-hook-interval"]
        await self.ops_test.model.set_config({"update-status-hook-interval": "10s"})
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        """On exit, the update status interval is reverted to its original value."""
        await self.ops_test.model.set_config({"update-status-hook-interval": self.revert_to})
