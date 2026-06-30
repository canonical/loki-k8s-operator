# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
import pytest
from interface_tester import InterfaceTester


@pytest.mark.skip(
    reason="grafana_datasource interface v1 schema not yet defined in charm-relation-interfaces. "
    "See https://github.com/canonical/grafana-k8s-operator/pull/571"
)
def test_grafana_datasource_v1_interface(grafana_datasource_tester: InterfaceTester):
    grafana_datasource_tester.configure(
        interface_name="grafana_datasource",
        interface_version=1,
    )
    grafana_datasource_tester.run()
