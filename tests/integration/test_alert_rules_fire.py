#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import jubilant
import pytest
import yaml
from helpers import all_active_idle, is_loki_up, juju_show_unit, loki_alerts

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
resources = {
    "loki-image": METADATA["resources"]["loki-image"]["upstream-source"],
    "node-exporter-image": METADATA["resources"]["node-exporter-image"]["upstream-source"],
}


@pytest.mark.setup
def test_alert_rules_do_fire(juju: jubilant.Juju, loki_charm, loki_tester_charm):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    app_names = [loki_app_name, tester_app_name]

    juju.deploy(loki_charm, loki_app_name, resources=resources, trust=True)
    juju.deploy(loki_tester_charm, tester_app_name)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    juju.integrate(loki_app_name, tester_app_name)
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)

    # Trigger a log message to fire an alert on
    juju.run(f"{tester_app_name}/0", "log-error", params={"message": "Error logged!"})
    alerts = loki_alerts(juju, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )


def test_loki_scales_up(juju: jubilant.Juju):
    """Make sure Loki endpoints propagate on scaling."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"
    app_names = [loki_app_name, tester_app_name]

    juju.cli("scale-application", loki_app_name, "3")
    juju.wait(
        lambda s: all_active_idle(s, loki_app_name) and len(s.get_units(loki_app_name)) == 3,
        timeout=1000,
    )
    juju.wait(lambda s: all_active_idle(s, *app_names), timeout=1000)
    assert is_loki_up(juju, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on
    juju.run(f"{tester_app_name}/0", "log-error", params={"message": "Error logged!"})

    for unit_num in range(3):
        unit_alerts = loki_alerts(juju, "loki", unit_num=unit_num)
        assert all(
            key in alert["labels"].keys()
            for key in ["juju_application", "juju_model", "juju_model_uuid"]
            for alert in unit_alerts
        )


@pytest.mark.skip(reason="xfail")
def test_scale_down_to_zero_units(juju: jubilant.Juju):
    loki_app_name = "loki"
    juju.cli("scale-application", loki_app_name, "0")
    juju.wait(
        lambda s: all_active_idle(s, loki_app_name) and len(s.get_units(loki_app_name)) == 0,
        timeout=600,
    )

    loki_data_on_requirer_side = juju_show_unit(
        juju,
        "loki-tester/0",
        endpoint="logging",
        app_data_only=True,
    )

    assert "related-units" not in loki_data_on_requirer_side["relation-info"][0]
