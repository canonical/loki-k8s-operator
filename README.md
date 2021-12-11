# Loki Charmed Operator for K8s

[![Test Suite](https://github.com/canonical/loki-k8s-operator/actions/workflows/run_tests.yaml/badge.svg)](https://github.com/canonical/loki-k8s-operator/actions/workflows/run_tests.yaml)

## Description

[Loki](https://grafana.com/oss/loki/) is an open-source fully-featured logging stack. The Loki charmed operator deploys Loki in Kubernetes using [Juju, the Charmed Operator Lifecycle Manager (OLM).](https://juju.is/)


## Quick start

Create a Juju model for your operators, say "observability"

```bash
juju add-model observability
```

Deploy the Loki Operator from charmhub using the Juju command line interface:

```bash
juju deploy loki-k8s
```

If required, you can remove the deployment completely:

```bash
juju destroy-model -y observability --no-wait --force --destroy-storage
```
Note the `--destroy-storage` will delete any data stored by Loki in its persistent store.
