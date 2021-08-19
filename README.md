# Loki Operator for K8s

![tests](https://github.com/canonical/loki-operator/actions/workflows/run-tests.yaml/badge.svg)

## Description

The [Loki](https://grafana.com/oss/loki/) operator provides an open-source fully featured logging stack. This repository contains a Juju Charm for deploying Grafana Loki on Kubernetes clusters.


## Usage

Create a Juju model for your operators, say "loki-k8s"

```bash
$ juju add-model loki-k8s
```

The Loki Operator may be deployed using the Juju command line

```bash
$ juju deploy loki-k8s
```

If required, you can remove the deployment completely:

```bash
$ juju destroy-model -y loki-k8s --no-wait --force --destroy-storage
```
Note the `--destroy-storage` will delete any data stored by MySQL in its persistent store.

### Config

This charm implements the following optional configs:

- `target`: Which component Loki runs. Possible options: all, querier, ingester, query-frontend, or distributor.

And you can use it, like this:

```bash
$  juju deploy loki-k8s --config target=all
```


## Relations

This charm provides a `loki-push-api` relation so you can integrate this charm with others charms that requires a Loki logging stack.


## OCI Images

This charm by default uses the latest version of the [ubuntu/mysql](https://hub.docker.com/r/ubuntu/mysql) image.

