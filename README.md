# Loki Operator for K8s

[![Test Suite](https://github.com/canonical/loki-k8s-operator/actions/workflows/run_tests.yaml/badge.svg)](https://github.com/canonical/loki-k8s-operator/actions/workflows/run_tests.yaml)

## Description

The [Loki](https://grafana.com/oss/loki/) operator provides an open-source fully featured logging stack. This repository contains a Juju Charm for deploying Grafana Loki on Kubernetes clusters.


## Usage

Create a Juju model for your operators, say "lma"

```bash
    juju add-model lma
```

The Loki Operator may be deployed using the Juju command line

```bash
    juju deploy loki-k8s
```

If required, you can remove the deployment completely:

```bash
    juju destroy-model -y lma --no-wait --force --destroy-storage
```
Note the `--destroy-storage` will delete any data stored by Loki in its persistent store.


## Relations

Currently supported relations are:

- [Grafana](https://github.com/canonical/grafana-operator) aggregates
  logs obtained by Loki and provides a versatile dashboard to
  view these logs in configurable ways. Loki relates to
  Grafana over the `grafana_datasource` interface.
- [Alertmanager](https://github.com/canonical/alertmanager-operator)
  receives alerts from Loki, aggregates and deduplicates them,
  then forwards them to specified targets. Loki relates to
  Alertmanager over the `alertmanager_dispatch` interface.
- In addition, this Loki charm allows relations with any
  charm that supports the `loki_push_api` relation interface.


## OCI Images

This charm by default uses the latest stable version of the [grafana/loki](https://hub.docker.com/r/grafana/loki) image.

