#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import patch

import yaml


def tautology(*_, **__) -> bool:
    return True


k8s_resource_multipatch = patch.multiple(
    "charm.KubernetesComputeResourcesPatch",
    _namespace="test-namespace",
    _patch=tautology,
    is_ready=tautology,
)


class FakeProcessVersionCheck:
    def __init__(self, args):
        pass

    def wait_output(self):
        return ("v0.1.0", "")

    def wait(self):
        return ("v0.1.0", "")

def _written_group_names(context, state_out):
    """Return alert group names found in rendered Loki rule files."""
    fs = state_out.get_container("loki").get_filesystem(context)
    rules_dir = fs.joinpath("loki", "rules", "fake")
    if not rules_dir.exists():
        return set()

    rule_files = sorted(path for path in rules_dir.iterdir() if path.is_file())
    written_group_names = set()
    for rule_file in rule_files:
        written_rules = yaml.safe_load(rule_file.read_text())
        for group in written_rules["groups"]:
            written_group_names.add(group["name"])
    return written_group_names
