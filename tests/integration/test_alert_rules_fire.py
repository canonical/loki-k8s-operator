#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest
from helpers import is_loki_up, juju_show_unit, loki_alerts

logger = logging.getLogger(__name__)


def test_alert_rules_do_fire(
    juju: jubilant.Juju,
    loki_charm,
    loki_resources,
    loki_tester_charm,
):
    """Test basic functionality of Loki push API relation interface."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"

    juju.deploy(loki_charm, loki_app_name, resources=loki_resources, trust=True)
    juju.deploy(loki_tester_charm, tester_app_name)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    juju.integrate(loki_app_name, tester_app_name)

    juju.wait(
        lambda status: jubilant.all_active(status) and jubilant.all_agents_idle(status),
        timeout=10 * 60,
    )

    # Trigger a log message to fire an alert on
    juju.run(f"{tester_app_name}/0", "log-error", {"message": "Error logged!"})
    alerts = loki_alerts(juju, "loki")
    assert alerts, "no alerts fired in Loki after triggering log-error"
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )


def test_loki_scales_up(juju: jubilant.Juju):
    """Make sure Loki endpoints propagate on scaling."""
    loki_app_name = "loki"
    tester_app_name = "loki-tester"

    juju.cli("scale-application", loki_app_name, "3")
    juju.wait(
        lambda status: (
            jubilant.all_active(status)
            and jubilant.all_agents_idle(status)
            and len(status.apps[loki_app_name].units) == 3
        ),
        timeout=10 * 60,
    )
    assert is_loki_up(juju, loki_app_name, num_units=3)

    # Trigger a log message to fire an alert on
    juju.run(f"{tester_app_name}/0", "log-error", {"message": "Error logged!"})

    alerts_per_unit = [
        loki_alerts(juju, "loki", unit_num=i) for i in range(3)
    ]

    for unit_alerts in alerts_per_unit:
        assert unit_alerts, f"no alerts fired in Loki units after triggering log-error"
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
        lambda status: (
            jubilant.all_active(status)
            and jubilant.all_agents_idle(status)
            and len(status.apps[loki_app_name].units) == 0
        ),
        timeout=10 * 60,
    )

    loki_data_on_requirer_side = juju_show_unit(
        juju,
        "loki-tester/0",
        endpoint="logging",
        app_data_only=True,
    )

    assert "related-units" not in loki_data_on_requirer_side["relation-info"][0]
