# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import itertools
import json
import logging
import urllib.request
from pathlib import Path
from typing import List, Sequence, Union

import requests
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.test_charm_with_loki import (
    JUJU_MODEL_UUID_KEY,
    PROMTAIL_JOB_TEMPLATE,
)

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


def oci_image(metadata_file: Union[Path, str], image_name: str) -> str:
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


def all_combinations(sequence: Sequence[str]) -> List[Sequence[str]]:
    """Generates all combinations of a sequence of strings.

    For
    """
    combos: List[Sequence[str]] = []
    for i in range(1, len(sequence) + 1):
        combos.extend(itertools.combinations(sequence, r=i))
    return combos


async def run_in_loki_tester(ops_test: OpsTest, cmd):
    cmd_line = f"juju ssh --container loki-tester loki-tester/0 {cmd}"
    return await ops_test.run(*cmd_line.split(" "))


async def check_file_exists_in_loki_tester_unit(ops_test, file_path, file_name):
    return_code, stdout, stderr = await run_in_loki_tester(
        ops_test, f"ls -l {file_path}{file_name}| grep {file_name}"
    )
    return stdout and not stderr and return_code == 0


async def get_loki_address(ops_test, loki_app_name):
    # obtain the loki cluster IP to make direct api calls
    return_code, stdout, stderr = await ops_test.juju("status", "--format=json")
    try:
        jsn = json.loads(stdout)
        return jsn["applications"][loki_app_name]["units"][f"{loki_app_name}/0"]["address"]
    except Exception as e:
        raise RuntimeError(
            f"failed to fetch loki address; j status returned {return_code!r}"
            f"with {stdout!r}, {stderr!r}"
            f"Embedded error: {e}"
        )


def loki_api_query_range(job_name: str, loki_address: str):
    params = {"query": '{job="%s"}' % job_name}
    # loki_api_query_range goes from now to up to 1h ago, more
    # certain to capture something
    query_url = f"http://{loki_address}:3100/loki/api/v1/loki_api_query_range"
    jsn = requests.get(query_url, params=params).json()
    return jsn["data"]["result"]


def populate_template(template, result):
    juju_model_uuid = result["stream"][JUJU_MODEL_UUID_KEY]
    expected_stream = template.copy()
    expected_stream["juju_model"] = juju_model_name = result["stream"]["juju_model"]
    expected_stream[JUJU_MODEL_UUID_KEY] = juju_model_uuid
    expected_stream["job"] = PROMTAIL_JOB_TEMPLATE.format(
        uuid=juju_model_uuid, model_name=juju_model_name
    )
    return expected_stream
