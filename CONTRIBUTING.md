# Contributing to loki-operator

## Overview

This documents explains the processes and practices recommended for
contributing enhancements or bug fixing to the Loki Charmed Operator.


## Setup

A typical development setup for charms created with the [Charmed Operator Framework](https://juju.is/docs/sdk) contains:


- [Charmcraft](https://github.com/canonical/charmcraft) - Developer tooling for creating, building and publishing Charmed Operators
- [Juju](https://juju.is/) - a Charmed Operator Lifecycle Manager (OLM), used for deploying and managing operators
- [Multipass](https://multipass.run/) - a lightweight Ubuntu virtual machine manager (optional)
- [MicroK8s](https://microk8s.io/) - a low-ops Kubernetes distribution we’ll use for testing our Charmed Operator (optional if developing a Charmed Operator for Kubernetes)

Please [follow this guide](https://juju.is/docs/sdk/dev-setup) which will walk through the installation of these tools to get you started with charm development.


## Developing



- In our development practice we first open an issue explaining the use case before submitting a pull request.
- If you would like to chat with us about your use-cases or proposed
  implementation, you can reach us at
  [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
  The primary author of this charm is available on the Mattermost channel as
  `@jose-masson`.
- It is strongly recommended that prior to engaging in any enhancements
  to this charm you familiarise your self with [Juju](https://juju.is).
- Familiarising yourself with the
  [Charmed Operator Framework](https://juju.is/docs/sdk).
  library will help you a lot when working on PRs.
- All enhancements require review before being merged. Besides the
  code quality and test coverage, the review will also take into
  account the resulting user experience for Juju administrators using
  this charm. Please help us out in having easier reviews by rebasing
  onto the `main` branch, avoid merge commits and enjoy a linear Git
  history.
- To handle our virtualenvs we use [`tox`](https://tox.wiki/en/latest/#), so there is no need
  to deal with them manually. Tox will create, update, activate and deactivate virtualenvs for us.

### Testing

All tests can be executed by running `tox` without arguments.

Besides you can run individual test environments or tasks:

```bash
tox -e lint         # check your code complies to linting rules
tox -e static       # run static analysis
tox -e unit         # run unit tests
tox -e integration  # run integration tests
tox -e fmt          # update your code according to linting rules
```

Unit tests are implemented using the Operator Framework test [harness](https://ops.readthedocs.io/en/latest/#module-ops.testing).

### Build

In order to build the charm so it can be deployed in [MicroK8s](https://microk8s.io/) using [Juju](https://juju.is/), we use [charmcraft](https://juju.is/docs/sdk/setting-up-charmcraft).
So in the charm repository you have to run:

```bash
$ charmcraft pack
Packing charm 'loki-k8s_ubuntu-20.04-amd64.charm'...
Created 'loki-k8s_ubuntu-20.04-amd64.charm'.
```

## Code Overview

The core implementation of this charm is represented by the [`LokiOperatorCharm`](src/charm.py) class, which
responds to the following events:

- `install`: Here we patch k8s service.
- `config_change`: Here we configure the charm.
- `loki_pebble_ready`: Here we set up pebble layer and start the service
- `upgrade_charm`: Here we patch k8s service and configure the charm.
- `alertmanager_consumer.on.cluster_changed`: This event is provided by the AlertmanagerConsumer object. Here we configure the charm.


## Design Choices

This Loki charm does not support (yet) the distributed deployment, only the standalone one.
