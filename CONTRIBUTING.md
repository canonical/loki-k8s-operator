## Developing

Create and activate a virtualenv with the development requirements:

```bash
   virtualenv -p python3 venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
```

### Setup

A typical setup using [snaps](https://snapcraft.io/), for deployments to a [microk8s](https://microk8s.io/) cluster can be done using the following commands

```bash
    sudo snap install microk8s --classic
    microk8s.enable dns storage
    sudo snap install juju --classic
    juju bootstrap microk8s microk8s
    juju create-storage-pool operator-storage kubernetes storage-class=microk8s-hostpath
```

### Build

Install the charmcraft tool

```bash
    sudo snap install charmcraft
```

Build the charm in this git repository

```bash
    charmcraft pack
```

## Testing

Unit tests are implemented using the Operator Framework test [harness](https://ops.readthedocs.io/en/latest/#module-ops.testing). These tests may executed by doing:


```bash
    ./run_tests
```


## Code Overview

The core implementation of this charm is represented by the [`LokiOperatorCharm`](src/charm.py) class.
`LokiOperatorCharm` responds to the following events:

- `loki_pebble_ready`: Here we set up pebble layer and start the service
- `relation_joined` In this event (Provided by the object `LokiProvider`) we set the `loki_push_api` (`http://{self.unit_ip}:{self.charm.port}/loki/api/v1/push`) so it can be used by a Consumer charm that uses the `LokiConsumer` object.

Both clases `LokiProvider` and `LokiConsumer` are provided by the [`Loki library`](lib/charms/loki_k8s/v0/loki.py)


## Design Choices

This Loki charm does not support (yet) the distributed deployment, only the standalone one.
