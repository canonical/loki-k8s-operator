#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import patch


def tautology(*_, **__) -> bool:
    return True


k8s_resource_multipatch = patch.multiple(
    "charm.KubernetesComputeResourcesPatch",
    _namespace="test-namespace",
    _patch=tautology,
    is_ready=tautology,
)
