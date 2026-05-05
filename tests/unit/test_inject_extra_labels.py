"""Tests for ConsumerBase._inject_extra_labels_to_alert_rules using pytest-bdd."""


import yaml
from charms.loki_k8s.v1.loki_push_api import ConsumerBase
from pytest_bdd import given, scenarios, then, when

scenarios("features/inject_extra_labels.feature")


@given("rules", target_fixture="rules")
def given_rules(docstring):
    """Parse the alert rules from the docstring fixture."""
    return yaml.safe_load(docstring)


@when("extra labels are injected", target_fixture="modified_rules")
def when_extra_labels_injected(docstring, rules):
    """Inject extra labels using the method under test."""
    extra_labels = yaml.safe_load(docstring)

    return ConsumerBase._inject_extra_labels_to_alert_rules(
        alert_rules, extra_labels
    )


@then("modified rules match")
def then_modified_rules_match(modified_rules, docstring):
    """Verify every rule has the extra labels."""
    expected = yaml.safe_load(docstring)
    assert expected == modified_rules
