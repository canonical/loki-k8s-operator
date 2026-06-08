# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import subprocess
import time
import urllib.request
from typing import List, Optional
from urllib.error import HTTPError
from urllib.parse import urljoin

import jubilant
import requests
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def get_unit_address(juju: jubilant.Juju, app_name: str, unit_num: int) -> str:
    """Get the address of a specific unit."""
    status = juju.status()
    unit_name = f"{app_name}/{unit_num}"
    return status.apps[app_name].units[unit_name].address


def is_loki_up(juju: jubilant.Juju, app_name: str, num_units: int = 1) -> bool:
    """Check if Loki is responding on all units."""
    addresses = []
    for i in range(num_units):
        addr = get_unit_address(juju, app_name, i)
        if addr:
            addresses.append(addr)

    if len(addresses) != num_units:
        return False

    def get(url) -> bool:
        try:
            response = urllib.request.urlopen(url, data=None, timeout=2.0)
            return response.code == 200 and "version" in json.loads(response.read())
        except Exception:
            return False

    for _ in range(5):
        resp = [
            get(f"http://{address}:3100/loki/api/v1/status/buildinfo") for address in addresses
        ]
        if all(resp):
            return True
        time.sleep(1)
    return False


def loki_rules(juju: jubilant.Juju, app_name: str) -> dict:
    """Get alert rules from Loki."""
    address = get_unit_address(juju, app_name, 0)
    url = f"http://{address}:3100"
    try:
        response = urllib.request.urlopen(f"{url}/loki/api/v1/rules", data=None, timeout=2.0)
        if response.code == 200:
            return yaml.safe_load(response.read())
        return {}
    except HTTPError:
        return {}


def loki_services(juju: jubilant.Juju, app_name: str) -> dict:
    """Fetch the status of Loki services from loki HTTP api."""
    address = get_unit_address(juju, app_name, 0)
    url = f"http://{address}:3100/services"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            services = {}
            for line in response.text.split("\n"):
                if line.strip():
                    key, value = line.strip().split(" => ")
                    services[key.strip()] = value.strip()
            return services
        return {}
    except requests.exceptions.RequestException:
        return {}


def loki_config(juju: jubilant.Juju, app_name: str) -> dict:
    """Fetch the Loki configuration from loki HTTP api."""
    address = get_unit_address(juju, app_name, 0)
    url = f"http://{address}:3100/config"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return yaml.safe_load(response.text)
        return {}
    except requests.exceptions.RequestException:
        return {}


def loki_endpoint_request(
    juju: jubilant.Juju, app_name: str, endpoint: str, unit_num: int = 0
) -> str:
    """Make a request to a Loki endpoint."""
    address = get_unit_address(juju, app_name, unit_num)
    url = urljoin(f"http://{address}:3100/", endpoint)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        return ""
    except requests.exceptions.RequestException:
        return ""


def loki_api_query(
    juju: jubilant.Juju, app_name: str, query: str, unit_num: int = 0
) -> list:
    """Query Loki via the API."""
    address = get_unit_address(juju, app_name, unit_num)
    url = f"http://{address}:3100/loki/api/v1/query_range"
    params = {"query": query}
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()["data"]["result"]
        return []
    except requests.exceptions.RequestException:
        return []


def loki_alerts(juju: jubilant.Juju, app_name: str, unit_num: int = 0, retries: int = 3) -> list:
    """Get a list of alerts from a Prometheus-compatible endpoint."""
    address = get_unit_address(juju, app_name, unit_num)
    url = f"http://{address}:3100/prometheus/api/v1/alerts"

    alerts = []
    while retries > 0:
        try:
            alerts = json.loads(urllib.request.urlopen(url, data=None, timeout=2).read())["data"][
                "alerts"
            ]
            if alerts:
                break
        except Exception:
            pass
        retries -= 1
        time.sleep(2)

    return alerts


def get_alertmanager_alerts(
    juju: jubilant.Juju, unit_name: str, unit_num: int, retries: int = 3
) -> List[dict]:
    """Get a list of alerts from Alertmanager."""
    address = get_unit_address(juju, unit_name, unit_num)
    url = f"http://{address}:9093/api/v2/alerts"
    alerts: List[dict] = []
    while retries > 0:
        try:
            alerts = json.loads(urllib.request.urlopen(url, data=None, timeout=2).read())
            if alerts:
                break
        except Exception:
            pass
        retries -= 1
        time.sleep(2)

    return alerts


def oci_image(charmcraft_file: str, image_name: str) -> str:
    """Find upstream source for a container image."""
    metadata = yaml.safe_load(open(charmcraft_file).read())
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


def juju_show_unit(
    juju: jubilant.Juju,
    unit_name: str,
    *,
    endpoint: Optional[str] = None,
    related_unit: Optional[str] = None,
    app_data_only: bool = False,
) -> dict:
    """Helper function for obtaining output of `juju show-unit`."""
    args = ["show-unit", unit_name]
    if endpoint:
        args.extend(["--endpoint", endpoint])
    if related_unit:
        args.extend(["--related-unit", related_unit])
    if app_data_only:
        args.append("--app")
    result = juju.cli(*args)
    return yaml.safe_load(result)[unit_name]


def generate_log_file(
    model_name: str, app_name: str, unit_num: int, container_name: str, filepath: str
) -> bytes:
    """Generate a log file in a container."""
    cmd = [
        "juju",
        "ssh",
        "--model",
        model_name,
        "--container",
        container_name,
        f"{app_name}/{unit_num}",
        "flog",
        "-t",
        "log",
        "-w",
        "-o",
        filepath,
    ]
    try:
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise e
    return res.stdout


def get_pebble_plan(
    model_name: str, app_name: str, unit_num: int, container_name: str
) -> str:
    """Get the pebble plan from a container."""
    cmd = [
        "juju",
        "ssh",
        "--model",
        model_name,
        "--container",
        container_name,
        f"{app_name}/{unit_num}",
        "./charm/bin/pebble",
        "plan",
    ]
    try:
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise e
    return res.stdout.decode("utf-8")


def delete_pod(model_name: str, app_name: str, unit_num: int) -> bool:
    """Delete a pod using kubectl."""
    cmd = [
        "kubectl",
        "delete",
        "pod",
        f"{app_name}-{unit_num}",
        "-n",
        model_name,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise e


def get_traces(tempo_host: str, service_name: str = "tracegen-otlp_http", tls: bool = True):
    """Get traces directly from Tempo REST API."""
    url = f"{'https' if tls else 'http'}://{tempo_host}:3200/api/search?tags=service.name={service_name}"
    req = requests.get(url, verify=False)
    assert req.status_code == 200
    traces = json.loads(req.text)["traces"]
    return traces


@retry(stop=stop_after_attempt(15), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_traces_patiently(tempo_host: str, service_name: str = "tracegen-otlp_http", tls: bool = True):
    """Get traces directly from Tempo REST API, with retries."""
    traces = get_traces(tempo_host, service_name=service_name, tls=tls)
    assert len(traces) > 0
    return traces


def get_application_ip(juju: jubilant.Juju, app_name: str) -> str:
    """Get the application IP address."""
    status = juju.status()
    return status.apps[app_name].address
