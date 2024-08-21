#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import patch

from ops import ActiveStatus


def tautology(*_, **__) -> bool:
    return True


k8s_resource_multipatch = patch.multiple(
    "charm.KubernetesComputeResourcesPatch",
    _namespace="test-namespace",
    _patch=tautology,
    is_ready=tautology,
    get_status=lambda _: ActiveStatus(),
)


class FakeProcessVersionCheck:
    def __init__(self, args):
        pass

    def wait_output(self):
        return ("v0.1.0", "")

    def wait(self):
        return ("v0.1.0", "")
