# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: the charm's TLS certificate covers every hostname it advertises."""

import json
from unittest.mock import patch

from charms.tls_certificates_interface.v4.tls_certificates import (
    LIBID,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    generate_csr,
    generate_private_key,
)
from ops.testing import Relation, Secret, State

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


def test_upgrade_charm_replaces_a_stale_csr_with_the_current_sans(context, loki_container):
    """A refresh that changes the requested SANs must re-send the CSR without waiting for a relation event."""
    # GIVEN a certificates relation holding a CSR made by an older charm revision (unit FQDN only)
    private_key = generate_private_key()
    stale_csr = generate_csr(
        private_key=private_key, common_name="loki", sans_dns=frozenset({UNIT_FQDN})
    )
    relation = Relation(
        "certificates",
        remote_app_name="ssc",
        local_unit_data={
            "certificate_signing_requests": json.dumps(
                [{"certificate_signing_request": str(stale_csr), "ca": False}]
            )
        },
    )
    key_secret = Secret(
        tracked_content={"private-key": str(private_key)},
        label=f"{LIBID}-private-key-0-certificates",
        owner="unit",
    )
    state_in = State(containers=[loki_container], relations=[relation], secrets=[key_secret])

    # WHEN the charm is upgraded
    with patch("socket.getfqdn", new=lambda *args: UNIT_FQDN):
        state_out = context.run(context.on.upgrade_charm(), state_in)

    # THEN a CSR covering both the unit hostname and the service hostname is requested
    sent = json.loads(
        state_out.get_relation(relation.id).local_unit_data["certificate_signing_requests"]
    )
    sans = {
        san
        for entry in sent
        for san in CertificateRequestAttributes.from_csr(
            CertificateSigningRequest.from_string(entry["certificate_signing_request"]), False
        ).sans_dns
        or []
    }
    assert {UNIT_FQDN, SERVICE_HOSTNAME} <= sans
