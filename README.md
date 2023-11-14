# Loki Charmed Operator for K8s

[![CharmHub Badge](https://charmhub.io/loki-k8s/badge.svg)](https://charmhub.io/loki-k8s)
[![Release](https://github.com/canonical/loki-k8s-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/loki-k8s-operator/actions/workflows/release.yaml)
[![Discourse Status](https://img.shields.io/discourse/status?server=https%3A%2F%2Fdiscourse.charmhub.io&style=flat&label=CharmHub%20Discourse)](https://discourse.charmhub.io)

## Description

[Loki](https://grafana.com/oss/loki/) is an open-source fully-featured logging system. This Loki charmed operator handles installation, scaling, configuration, optimisation, networking, service mesh, observability, and Day 2 operations specific to [Loki](https://grafana.com/docs/loki/latest/) using [Juju](https://juju.is) and the [Charmed Operator Lifecycle Manager (OLM)](https://juju.is/docs/olm).

On the principle that an operator should *"do one thing and do it well"*, this operator drives Loki application only. However, it can be composed with other operators to deliver a complex application or service. Because operators package expert knowledge in a reusable and shareable form, they hugely simplify software management and operations.



## Getting started

### Basic deployment

Create a Juju model for your operator, say "observability"

```bash
juju add-model observability
```

The Loki Charmed Operator may be deployed using the Juju command line in a quite very way.

```bash
juju deploy loki-k8s --channel=stable
```


### Checking deployment status

Once the Charmed Operator is deployed, the status can be checked running:

```bash
juju status --color --relations
```


```bash
$ juju status --color --relations

Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  10:39:52-03:00

App       Version  Status   Scale  Charm     Channel  Rev  Address         Exposed  Message
loki-k8s  2.4.1    waiting      1  loki-k8s  stable    47  10.152.183.195  no       waiting for container

Unit         Workload  Agent  Address      Ports  Message
loki-k8s/0*  active    idle   10.1.36.115
```



### Loki HTTP API

Loki Charmed Operator exposes its [HTTP API](https://grafana.com/docs/loki/latest/api/) over port 3100.


#### Example 1 - Get Loki version:

`/loki/api/v1/status/buildinfo` exposes the build information in a JSON object.
The fields are `version`, `revision`, `branch`, `buildDate`, `buildUser`, and `goVersion`.

```bash
loki_ip=$(juju status loki-k8s/0 | grep "loki-k8s/0" | awk '{print $4}')

curl http://$loki_ip:3100/loki/api/v1/status/buildinfo
{"version":"2.4.1","revision":"f61a4d261","branch":"HEAD","buildUser":"root@39a6e600b2df","buildDate":"2021-11-08T13:09:51Z","goVersion":""}
```



#### Example 2 - Send logs entries to Loki with curl:

`/loki/api/v1/push` is the endpoint used to send log entries to Loki. The default behavior is for the POST body to be a snappy-compressed protobuf message.
Alternatively, if the `Content-Type` header is set to `application/json`, a JSON post body can be sent in the following format:

```bash
loki_ip=$(juju status loki-k8s/0 | grep "loki-k8s/0" | awk '{print $4}')

curl -v -H "Content-Type: application/json" -XPOST -s "http://$loki_ip:3100/loki/api/v1/push" --data-raw \
  '{"streams": [{ "stream": { "foo": "bar2" }, "values": [ [ "1570818238000000000", "fizzbuzz" ] ] }]}'
```


#### Example 3 - Send logs entries to Loki with Promtail:

[Promtail](https://grafana.com/docs/loki/latest/clients/promtail/) is an agent which ships the contents of local logs to Loki. It is usually deployed to every machine that has applications needed to be monitored.

It primarily:

- Discovers targets
- Attaches labels to log streams
- Pushes them to the Loki instance.

Currently, Promtail can tail logs from two sources: local log files and the systemd journal (on AMD64 machines only).

To set up a Promtail instance to work with Loki Charmed Operator please refer to [Configuring Promtail documentation](https://grafana.com/docs/loki/latest/clients/promtail/configuration/). Anyway the most important part is the `clients` section in Promtail config file, for instance:

```yaml
clients:
  - url: http://<LOKI_ADDRESS>:3100/loki/api/v1/push
```



## Relations

### Overview

Relations provide a means to integrate applications and enable a simple communications channel.
Loki Charmed Operator supports the following:


### Provides

#### Logging

```yaml
  logging:
    interface: loki_push_api
```

Loki Charmed Operator may receive logs from any charm that supports the `loki_push_api` relation interface.

Let's say that we have a Charmed Operator that implements the other side (`requires`) of the relation, for instance [Zinc](https://charmhub.io/zinc-k8s)
After deploying this charm, we can relate `Loki` and `Zinc` through `loki_push_api` relation interface:

```bash
juju relate zinc-k8s loki-k8s
```

And verify the relation between both charms is created:

```bash
$ juju status --relations

Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  10:57:01-03:00

App       Version  Status  Scale  Charm     Channel  Rev  Address         Exposed  Message
loki-k8s  2.4.1    active      1  loki-k8s  stable    47  10.152.183.168  no
zinc-k8s  0.3.5    active      1  zinc-k8s  stable    45  10.152.183.144  no

Unit         Workload  Agent      Address      Ports  Message
loki-k8s/0*  active    executing  10.1.36.79
zinc-k8s/0*  active    executing  10.1.36.123

Relation provider  Requirer          Interface      Type     Message
loki-k8s:logging   zinc-k8s:logging  loki_push_api  regular
```

Once the relation is established, Zinc charm can start sending logs to Loki charm.


#### Grafana-source

```yaml
  grafana-source:
    interface: grafana_datasource
    optional: true
```

The [Grafana Charmed Operator](https://github.com/canonical/grafana-k8s-operator) aggregates logs obtained by Loki and provides a versatile dashboard to view these logs in configurable ways.
Loki relates to Grafana over the `grafana_datasource` interface.

For example, let's say that we have already deployed the [Grafana Charmed Operator](https://charmhub.io/grafana-k8s) in our `observability` model.
The way to relate Loki and Grafana is again very simple:

```bash
juju relate grafana-k8s:grafana-source loki-k8s:grafana-source
```

And verify the relation between both charms is created:

```bash
$ juju status --relations

Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  11:09:08-03:00

App          Version  Status  Scale  Charm        Channel  Rev  Address         Exposed  Message
grafana-k8s  9.2.1    active      1  grafana-k8s  stable    52  10.152.183.40   no
loki-k8s     2.4.1    active      1  loki-k8s     stable    47  10.152.183.168  no

Unit            Workload  Agent  Address     Ports  Message
grafana-k8s/0*  active    idle   10.1.36.93
loki-k8s/0*     active    idle   10.1.36.79

Relation provider        Requirer                    Interface           Type     Message
grafana-k8s:grafana      grafana-k8s:grafana         grafana_peers       peer
loki-k8s:grafana-source  grafana-k8s:grafana-source  grafana_datasource  regular
```


#### Metrics-endopoint

```yaml
  metrics-endpoint:
    interface: prometheus_scrape
```

This Loki Charmed Operator provides a metrics endpoint so a charm that implements the other side of the relation (`requires`), for instance [Prometheus Charmed Operator](https://charmhub.io/prometheus-k8s) can scrape Loki metrics.

For instance, let's say that we have already deployed the [Prometheus Charmed Operator](https://charmhub.io/prometheus-k8s) in our `observability` model.
The way to relate Loki and Promethes is again very simple:

```bash
juju relate prometheus-k8s loki-k8s
```


```bash
$ juju status --relations

Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  11:25:19-03:00

App             Version  Status  Scale  Charm           Channel  Rev  Address         Exposed  Message
grafana-k8s     9.2.1    active      1  grafana-k8s     stable    52  10.152.183.40   no
loki-k8s        2.4.1    active      1  loki-k8s        stable    47  10.152.183.168  no
prometheus-k8s  2.33.5   active      1  prometheus-k8s  stable    79  10.152.183.144  no

Unit               Workload  Agent  Address     Ports  Message
grafana-k8s/0*     active    idle   10.1.36.93
loki-k8s/0*        active    idle   10.1.36.79
prometheus-k8s/0*  active    idle   10.1.36.84

Relation provider                Requirer                         Interface           Type     Message
grafana-k8s:grafana              grafana-k8s:grafana              grafana_peers       peer
loki-k8s:grafana-source          grafana-k8s:grafana-source       grafana_datasource  regular
loki-k8s:metrics-endpoint        prometheus-k8s:metrics-endpoint  prometheus_scrape   regular
prometheus-k8s:prometheus-peers  prometheus-k8s:prometheus-peers  prometheus_peers    peer
```


#### Grafana-dashboard


```yaml
  grafana-dashboard:
    interface: grafana_dashboard
```

Loki Charmed Operator may send its own Dashboards to Grafana by using this relation.

After relating both charms this way:

```bash
juju relate grafana-k8s:grafana-dashboard loki-k8s:grafana-dashboard
```

You will be able to check that the relation is established, and see the Loki Dashboard in Grafana UI.


```bash
$ juju status --relations

Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  13:21:21-03:00

App             Version  Status  Scale  Charm           Channel  Rev  Address         Exposed  Message
grafana-k8s     9.2.1    active      1  grafana-k8s     stable    52  10.152.183.40   no
loki-k8s        2.4.1    active      1  loki-k8s        stable    47  10.152.183.168  no
prometheus-k8s  2.33.5   active      1  prometheus-k8s  stable    79  10.152.183.144  no

Unit               Workload  Agent  Address     Ports  Message
grafana-k8s/0*     active    idle   10.1.36.85
loki-k8s/0*        active    idle   10.1.36.97
prometheus-k8s/0*  active    idle   10.1.36.67

Relation provider                Requirer                         Interface           Type     Message
grafana-k8s:grafana              grafana-k8s:grafana              grafana_peers       peer
loki-k8s:grafana-dashboard       grafana-k8s:grafana-dashboard    grafana_dashboard   regular
loki-k8s:grafana-source          grafana-k8s:grafana-source       grafana_datasource  regular
loki-k8s:metrics-endpoint        prometheus-k8s:metrics-endpoint  prometheus_scrape   regular
prometheus-k8s:prometheus-peers  prometheus-k8s:prometheus-peers  prometheus_peers    peer
```



### Requires

#### Alertmanager

[Alertmanager](https://charmhub.io/alertmanager-k8s) receives alerts from Loki, aggregates and deduplicates them, then forwards them to specified targets.
Loki Charmed Operator relates to Alertmanager over the `alertmanager_dispatch` interface.

Let's assume the we have already deployed Alertmanager Charmed Operator in our `obsevability` model, and relate it with Loki:

```bash
juju relate alertmanager-k8s loki-k8s
```

We can check the relation is established:

```bash
juju status --color --relations
```

```bash
$ juju status --relations
Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  13:27:18-03:00

App               Version  Status   Scale  Charm             Channel  Rev  Address         Exposed  Message
alertmanager-k8s  0.23.0   waiting      1  alertmanager-k8s  stable    36  10.152.183.56   no       waiting for container
grafana-k8s       9.2.1    active       1  grafana-k8s       stable    52  10.152.183.40   no
loki-k8s          2.4.1    active       1  loki-k8s          stable    47  10.152.183.168  no
prometheus-k8s    2.33.5   active       1  prometheus-k8s    stable    79  10.152.183.144  no

Unit                 Workload  Agent      Address      Ports  Message
alertmanager-k8s/0*  active    idle       10.1.36.113
grafana-k8s/0*       active    idle       10.1.36.85
loki-k8s/0*          active    executing  10.1.36.97
prometheus-k8s/0*    active    idle       10.1.36.67

Relation provider                Requirer                         Interface              Type     Message
alertmanager-k8s:alerting        loki-k8s:alertmanager            alertmanager_dispatch  regular
alertmanager-k8s:replicas        alertmanager-k8s:replicas        alertmanager_replica   peer
grafana-k8s:grafana              grafana-k8s:grafana              grafana_peers          peer
loki-k8s:grafana-dashboard       grafana-k8s:grafana-dashboard    grafana_dashboard      regular
loki-k8s:grafana-source          grafana-k8s:grafana-source       grafana_datasource     regular
loki-k8s:metrics-endpoint        prometheus-k8s:metrics-endpoint  prometheus_scrape      regular
prometheus-k8s:prometheus-peers  prometheus-k8s:prometheus-peers  prometheus_peers       peer
```

#### Ingress

```yaml
  ingress:
    interface: ingress_per_unit
    limit: 1
```

Interactions with the Loki charm can not be assumed to originate within the same Juju model, let alone the same Kubernetes cluster, or even the same Juju cloud. Hence the Loki charm also supports an Ingress relation. There are multiple use cases that require an ingress, in particular
- Querying the Loki HTTP API endpoint across network boundaries.
- Self monitoring of Loki that *must* happen across network boundaries to ensure robustness of self monitoring.
- Supporting the Loki push API.

Loki typical needs a "per unit" Ingress. This per unit ingress is necessary since Loki exposes it loki push api endpoint on a per unit basis. A per unit ingress relation is available in the [traefik-k8s](https://charmhub.io/traefik-k8s) charm and this Loki charm does support that relation over [`ingress_per_unit`](https://charmhub.io/traefik-k8s/libraries/ingress_per_unit) interface.


Let's assume the we have already deployed Traefik Charmed Operator in our `obsevability` model, and relate it with Loki:

```bash
juju relate traefik-k8s loki-k8s
```

We can check the relation is established:

```bash
juju status --color --relations
```

```bash
$ juju status --relations
Model          Controller           Cloud/Region        Version  SLA          Timestamp
observability  charm-dev-batteries  microk8s/localhost  3.0.2    unsupported  15:46:43-03:00

App               Version  Status  Scale  Charm             Channel  Rev  Address         Exposed  Message
alertmanager-k8s  0.23.0   active      1  alertmanager-k8s  stable    36  10.152.183.56   no
grafana-k8s       9.2.1    active      1  grafana-k8s       stable    52  10.152.183.40   no
loki-k8s          2.4.1    active      1  loki-k8s          stable    47  10.152.183.168  no
prometheus-k8s    2.33.5   active      1  prometheus-k8s    stable    79  10.152.183.144  no
traefik-k8s                active      1  traefik-k8s       stable    93  192.168.122.10  no

Unit                 Workload  Agent      Address      Ports  Message
alertmanager-k8s/0*  active    idle       10.1.36.95
grafana-k8s/0*       active    executing  10.1.36.121
loki-k8s/0*          active    idle       10.1.36.116
prometheus-k8s/0*    active    idle       10.1.36.80
traefik-k8s/0*       active    idle       10.1.36.122

Relation provider                Requirer                         Interface              Type     Message
alertmanager-k8s:alerting        loki-k8s:alertmanager            alertmanager_dispatch  regular
alertmanager-k8s:replicas        alertmanager-k8s:replicas        alertmanager_replica   peer
grafana-k8s:grafana              grafana-k8s:grafana              grafana_peers          peer
loki-k8s:grafana-dashboard       grafana-k8s:grafana-dashboard    grafana_dashboard      regular
loki-k8s:grafana-source          grafana-k8s:grafana-source       grafana_datasource     regular
loki-k8s:metrics-endpoint        prometheus-k8s:metrics-endpoint  prometheus_scrape      regular
prometheus-k8s:prometheus-peers  prometheus-k8s:prometheus-peers  prometheus_peers       peer
traefik-k8s:ingress-per-unit     loki-k8s:ingress                 ingress_per_unit       regular
```


## OCI Images

Every release of the Loki Charmed Operator uses the latest stable version of [grafana/loki](https://hub.docker.com/r/grafana/loki) at the time of release.


## Official Documentation

For further details about Loki configuration and usage, please refer to [Grafana Loki Documentation](https://grafana.com/docs/loki/latest/)
