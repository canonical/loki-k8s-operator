# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: the charm's TLS certificate covers every hostname it advertises."""

from unittest.mock import patch

from ops.testing import State

UNIT_FQDN = "loki-0.loki-k8s-endpoints.cos-lite.svc.cluster.local"
SERVICE_HOSTNAME = "loki-k8s-endpoints.cos-lite.svc.cluster.local"


def test_csr_requests_a_san_for_the_bare_service_hostname(context, loki_container):
    # GIVEN a charm whose unit FQDN includes the usual k8s unit prefix
    state_in = State(containers=[loki_container])

    # WHEN we inspect the CSR attributes built at charm init
    # (patched here, last, so it takes precedence over conftest's own dot-less default)
    with patch("socket.getfqdn", new=lambda *args: UNIT_FQDN):
        with context(context.on.update_status(), state_in) as mgr:
            charm = mgr.charm

            # THEN the SAN list includes both the unit-pinned hostname...
            assert UNIT_FQDN in charm._csr_attributes.sans_dns
            # ...and the bare k8s service hostname used by `_service_url`
            assert SERVICE_HOSTNAME in charm._csr_attributes.sans_dns


def test_service_url_hostname_is_always_a_requested_san(context, loki_container):
    """Guard against the SAN list and `_service_url` silently drifting apart again."""
    state_in = State(containers=[loki_container])

    with patch("socket.getfqdn", new=lambda *args: UNIT_FQDN):
        with context(context.on.update_status(), state_in) as mgr:
            charm = mgr.charm
            service_hostname = charm._service_hostname

            assert service_hostname == SERVICE_HOSTNAME
            assert service_hostname in charm._csr_attributes.sans_dns
