# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import itertools
import json
import logging
import urllib.request
from pathlib import Path

import yaml
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


def get_logpy_path() -> Path:
    """Return the Path to log.py file in loki-tester."""
    pth = Path(__file__).parent.resolve() / "loki_tester" / "src" / "log.py"
    print(pth)
    assert pth.exists(), pth
    return pth.absolute()


def oci_image(metadata_file: str, image_name: str) -> str:
    """Find upstream source for a container image.

    Args:
        metadata_file: string path of metadata YAML file relative
            to top level charm directory
        image_name: OCI container image string name as defined in
            metadata.yaml file

    Returns:
        upstream image source

    Raises:
        FileNotFoundError: if metadata_file path is invalid
        ValueError: if upstream source for image name can not be found
    """
    metadata = yaml.safe_load(Path(metadata_file).read_text())

    resources = metadata.get("resources", {})
    if not resources:
        raise ValueError("No resources found")

    image = resources.get(image_name, {})
    if not image:
        raise ValueError(f"{image_name} image not found")

    upstream_source = image.get("upstream-source", "")
    if not upstream_source:
        raise ValueError("Upstream source not found")

    return upstream_source


async def loki_rules(ops_test, app_name) -> dict:
    address = await get_unit_address(ops_test, app_name, 0)
    url = f"http://{address}:3100"

    try:
        response = urllib.request.urlopen(f"{url}/loki/api/v1/rules", data=None, timeout=2.0)
        if response.code == 200:
            return yaml.safe_load(response.read())
        return {}
    except urllib.error.HTTPError:
        return {}


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


def all_combinations(sequence):
    combos = []
    for i in range(1, len(sequence) + 1):
        combos.extend(map(lambda subseq: ",".join(subseq), itertools.combinations(sequence, r=i)))
    return combos
