# Contributing to loki-operator

The intended use case of this operator is to be deployed in K8s.


## Overview

This documents explains the processes and practices recommended for
contributing enhancements to the Loki charm.

- Generally, before developing enhancements to this charm, you should consider
  opening an issue explaining your use case.
- If you would like to chat with us about your use-cases or proposed
  implementation, you can reach us at
  [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
  The primary author of this charm is available on the Mattermost channel as
  `@jose-masson`.
- It is strongly recommended that prior to engaging in any enhancements
  to this charm you familiarise your self with Juju.
- Familiarising yourself with the
  [Charmed Operator Framework](https://juju.is/docs/sdk).
  library will help you a lot when working on PRs.
- All enhancements require review before being merged. Besides the
  code quality and test coverage, the review will also take into
  account the resulting user experience for Juju administrators using
  this charm. Please help us out in having easier reviews by rebasing
  onto the `main` branch, avoid merge commits and enjoy a linear Git
  history.


### Setup

A typical setup using [snaps](https://snapcraft.io/), for deployments to a [microk8s](https://microk8s.io/) cluster can be done using the following commands

```bash
    sudo snap install microk8s --classic
    microk8s.enable dns storage
    sudo snap install juju --classic
    juju bootstrap microk8s microk8s
    juju create-storage-pool operator-storage kubernetes storage-class=microk8s-hostpath
```


## Developing

Create and activate a virtualenv with the development requirements:

```bash
   virtualenv -p python3 venv
   source venv/bin/activate
   pip install -r requirements.txt
```


Later on, upgrade packages as needed

```bash
   pip install --upgrade -r requirements.txt
```


### Testing
All tests can be executed by running `tox` without arguments.

To run individual test environments:

```shell
tox -e prettify  # update your code according to linting rules
tox -e lint  # check your code complies to linting rules
tox -e static # run static analysis
tox -e unit  # run unit tests
```

Unit tests are implemented using the Operator Framework test [harness](https://ops.readthedocs.io/en/latest/#module-ops.testing).

### Build

Install the [charmcraft tool](https://juju.is/docs/sdk/setting-up-charmcraft) and build the charm in this git repository:

```bash
    charmcraft pack
```

## Code Overview

The core implementation of this charm is represented by the [`LokiOperatorCharm`](src/charm.py) class.
`LokiOperatorCharm` responds to the following events:

- `loki_pebble_ready`: Here we set up pebble layer and start the service
- `relation_joined` In this event (Provided by the object `LokiProvider`) we set the `loki_push_api` (`http://{self.unit_ip}:{self.charm.port}/loki/api/v1/push`) so it can be used by a Consumer charm that uses the `LokiConsumer` object.

Both clases `LokiProvider` and `LokiConsumer` are provided by the [`Loki library`](lib/charms/loki_k8s/v0/loki.py)


## Design Choices

This Loki charm does not support (yet) the distributed deployment, only the standalone one.
