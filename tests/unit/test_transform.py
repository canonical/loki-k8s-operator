# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest.mock
from pathlib import PosixPath

import pytest
from charms.loki_k8s.v0.loki_push_api import CosTool
from ops.charm import CharmBase
from ops.testing import Context
from scenario import State


class ToolProviderCharm(CharmBase):
    """Container charm for running the integration test."""

    def __init__(self, *args):
        super().__init__(*args)
        self.tool = CosTool(self)


TOOL_PROVIDER_META = {"name": "tool-provider"}


@pytest.fixture
def tool_provider_context():
    return Context(ToolProviderCharm, meta=TOOL_PROVIDER_META)


@unittest.mock.patch("platform.processor", lambda: "teakettle")
def test_disable_on_invalid_arch(tool_provider_context):
    """When given an invalid arch, the tool should be disabled."""
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        assert charm.tool.path is None
        assert charm.tool._disabled is True


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_gives_path_on_valid_arch(tool_provider_context):
    """When given a valid arch, it should return the binary path."""
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        assert isinstance(charm.tool.path, PosixPath)


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_setup_transformer(tool_provider_context):
    """When setup it should know the path to the binary."""
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        assert isinstance(charm.tool.path, PosixPath)
        p = str(charm.tool.path)
        assert p.endswith("cos-tool-amd64")


@unittest.mock.patch("platform.processor", lambda: "x86_64")
@unittest.mock.patch("subprocess.run")
def test_returns_original_expression_when_subprocess_call_errors(mock_run, tool_provider_context):
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=10, cmd="cos-tool", stderr=""
    )

    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        output = charm.tool.apply_label_matchers(
            {
                "groups": [
                    {
                        "alert": "CPUOverUse",
                        "expr": '{job="foo"} |= "info"',
                        "for": "0m",
                        "labels": {
                            "severity": "Low",
                            "juju_model": "None",
                            "juju_model_uuid": "f2c1b2a6-e006-11eb-ba80-0242ac130004",
                            "juju_application": "consumer-tester",
                        },
                        "annotations": {
                            "summary": "Instance {{ $labels.instance }} CPU over use",
                            "description": "{{ $labels.instance }} of job "
                            "{{ $labels.job }} has used too much CPU.",
                        },
                    }
                ]
            }
        )
        assert output["groups"][0]["expr"] == '{job="foo"} |= "info"'


@unittest.mock.patch("platform.processor", lambda: "invalid")
def test_uses_original_expression_when_binary_missing(tool_provider_context):
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        output = charm.tool.apply_label_matchers(
            {
                "groups": [
                    {
                        "alert": "CPUOverUse",
                        "expr": '{job="foo"} |= "info"',
                        "for": "0m",
                        "labels": {
                            "severity": "Low",
                            "juju_model": "None",
                            "juju_model_uuid": "f2c1b2a6-e006-11eb-ba80-0242ac130004",
                            "juju_application": "consumer-tester",
                        },
                        "annotations": {
                            "summary": "Instance {{ $labels.instance }} CPU over use",
                            "description": "{{ $labels.instance }} of job "
                            "{{ $labels.job }} has used too much CPU.",
                        },
                    }
                ]
            }
        )
        assert output["groups"][0]["expr"] == '{job="foo"} |= "info"'


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_fetches_the_correct_expression(tool_provider_context):
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        output = charm.tool.inject_label_matchers(
            '{env="production"}', {"juju_model": "some_juju_model"}
        )
        assert output == '{env="production", juju_model="some_juju_model"}'


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_handles_comparisons(tool_provider_context):
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        output = charm.tool.inject_label_matchers(
            'rate({env="production"} |= "info" [10m]) > 1', {"juju_model": "some_juju_model"}
        )
        assert (
            output == '(rate({env="production", juju_model="some_juju_model"} |= "info"[10m]) > 1)'
        )


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_handles_multiple_labels(tool_provider_context):
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        keys = {
            "juju_model": "some_juju_model",
            "juju_model_uuid": "123ABC",
            "juju_application": "some_application",
            "juju_unit": "some_application/1",
        }
        output = charm.tool.inject_label_matchers('{env="production"}', keys)
        assert all('{}="{}"'.format(k, v) in output for k, v in keys.items())


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_returns_errors_on_bad_rule_file(tool_provider_context):
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        valid, errs = charm.tool.validate_alert_rules(
            {
                "groups": [
                    {
                        "alert": "BadSyntax",
                        "expr": "rate{) > 0.12",
                    }
                ]
            }
        )
        # Validation should fail for bad syntax
        assert valid is False


@unittest.mock.patch("platform.processor", lambda: "x86_64")
def test_successfully_validates_good_alert_rules(tool_provider_context):
    state = State()
    with tool_provider_context(tool_provider_context.on.start(), state) as mgr:
        charm = mgr.charm
        valid, errs = charm.tool.validate_alert_rules(
            {
                "groups": [
                    {
                        "name": "CPUOverUse",
                        "rules": [
                            {
                                "alert": "CPUOverUse",
                                "expr": 'rate({job="unit_test"} [5m]) > 0.12',
                                "for": "0m",
                                "labels": {
                                    "severity": "Low",
                                    "juju_model": "None",
                                    "juju_model_uuid": "f2c1b2a6-e006-11eb-ba80-0242ac130004",
                                    "juju_application": "consumer-tester",
                                },
                                "annotations": {
                                    "summary": "Instance {{ $labels.instance }} CPU over use",
                                    "description": "{{ $labels.instance }} of job "
                                    "{{ $labels.job }} has used too much CPU.",
                                },
                            }
                        ],
                    }
                ]
            }
        )
        assert errs == ""
        assert valid is True
