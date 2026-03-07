#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging

import jubilant
import pytest
import pytest_jubilant
from helpers import is_loki_up, loki_rules

logger = logging.getLogger(__name__)

resources = pytest_jubilant.get_resources()
app_name = "loki-k8s"
rules_app = "loki-tester"
rules_app2 = "loki-tester2"
rules_app3 = "loki-tester3"
rules_after_relation = None


@pytest.mark.abort_on_fail
def test_deploy(juju: jubilant.Juju, loki_charm):
    """Deploy Loki and ensure it doesn't have any rules yet.

    Assert on the unit status before any relations/configurations take place.
    """
    juju.deploy(loki_charm, app_name, resources=resources, trust=True)
    juju.wait(lambda s: jubilant.all_active(s, app_name), timeout=1000)
    assert juju.status().apps[app_name].units[f"{app_name}/0"].workload_status.current == "active"

    assert is_loki_up(juju, app_name)

    rules_before_relation = loki_rules(juju, app_name)
    assert len(rules_before_relation) == 0


@pytest.mark.abort_on_fail
def test_first_relation_one_alert_rule(juju: jubilant.Juju, loki_tester_charm):
    juju.deploy(loki_tester_charm, rules_app)

    # form a relation between loki and the app that provides rules
    juju.integrate(app_name, rules_app)

    juju.wait(lambda s: jubilant.all_active(s, app_name, rules_app), timeout=1000)
    global rules_after_relation
    rules_after_relation = loki_rules(juju, app_name)
    assert len(rules_after_relation) == 1


@pytest.mark.abort_on_fail
def test_second_relation_second_alert_rule(juju: jubilant.Juju, loki_tester_charm):
    juju.deploy(loki_tester_charm, rules_app2)

    # form a relation between loki and the app that provides rules
    juju.integrate(app_name, rules_app2)

    juju.wait(lambda s: jubilant.all_active(s, app_name, rules_app2), timeout=1000)

    rules_after_relation2 = loki_rules(juju, app_name)
    assert len(rules_after_relation2) == 2


@pytest.mark.abort_on_fail
def test_wrong_alert_rule(juju: jubilant.Juju, faulty_loki_tester_charm):
    juju.deploy(faulty_loki_tester_charm, rules_app3)

    # form a relation between loki and the app that provides rules
    juju.integrate(app_name, rules_app3)
    juju.wait(lambda s: jubilant.all_blocked(s, app_name), timeout=1000)
