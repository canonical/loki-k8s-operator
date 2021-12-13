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



- Prior to getting started on a pull request, we first encourage you to open an issue explaining the use case or bug.
  This gives other contributors a chance to weigh in early in the process.
- To author PRs you should know [what is jujuj](https://juju.is/#what-is-juju) and [how operators are written](https://juju.is/docs/sdk).
- The best way to get a head start is to join the conversation on [our mattermost channel](https://chat.charmhub.io/charmhub/channels/observability)!
  or [Discourse](https://discourse.charmhub.io/). The primary author of this charm is available on the Mattermost channel as `@jose-masson`.
- All enhancements require review before being merged. Besides the
  code quality and test coverage, the review will also take into
  account the resulting user experience for Juju administrators using
  this charm. To be able to merge you would have to rebase
  onto the `main` branch. We do this to avoid merge commits and to have a linear Git
  history.
- We use [`tox`](https://tox.wiki/en/latest/#) to manage all virtualenvs for the development lifecycle.

### Testing

All default tests can be executed by running `tox` without arguments.

You can also manually run specific test environment:

```bash
tox -e lint         # check your code complies to linting rules
tox -e static       # run static analysis
tox -e unit         # run unit tests
tox -e integration  # run integration tests
tox -e fmt          # update your code according to linting rules
```

Unit tests are written with the Operator Framework [test harness](https://ops.readthedocs.io/en/latest/#module-ops.testing).

### Build

In order to pack the charm locally so it could be deployed from a local path we use 
[charmcraft](https://juju.is/docs/sdk/setting-up-charmcraft).

From the charm's root folder:

```bash
$ charmcraft pack
Packing charm 'loki-k8s_ubuntu-20.04-amd64.charm'...
Created 'loki-k8s_ubuntu-20.04-amd64.charm'.
```

## Code Overview

### Charm code
This charm is represented by the [`LokiOperatorCharm`](src/charm.py) class, which
responds to the following events:

#### Juju Events

- `install`: Makes sure the k8s service is using the correct ports.
- `config_change`: Configures the charm.
- `loki_pebble_ready`: Sets up the pebble layer and starts the service
- `upgrade_charm`: Patches the ports of the k8s service (just as `install`) and configures the charm (just as `config_change`).
- `alertmanager_consumer.on.cluster_changed`: This event is provided by the AlertmanagerConsumer. Here we configure the charm.


## Design Choices

This Loki charm does not support (yet) the distributed deployment, only the standalone one.
