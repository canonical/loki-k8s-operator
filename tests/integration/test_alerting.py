import asyncio
import logging
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
resources = {"loki-image": METADATA["resources"]["loki-image"]["upstream-source"]}


@pytest.mark.abort_on_fail
async def test_alert_rules_setup_by_loki_do_raise_alerts(
        ops_test, loki_charm, loki_tester_charm
):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    app_names = [loki_app_name, tester_app_name]

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
        ),
        ops_test.model.deploy(
            loki_tester_charm,
            application_name=tester_app_name,
        ),
    )

    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
        )
    )

    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")
