## Integrating Loki Charmed Operator

### Overview

This Loki Charmed Operator provides two libraries for integrating with other charms:

- [`loki_push_api`](https://charmhub.io/loki-k8s/libraries/loki_push_api)
- [`log_proxy`](https://charmhub.io/loki-k8s/libraries/log_proxy)


The `loki_push_api` library provides
[endpoint URL](https://grafana.com/docs/loki/latest/api/#post-lokiapiv1push)
to receive log from [Loki clients](https://grafana.com/docs/loki/latest/clients/) that relates
with this charm.

The Loki charm supports user-provided alert rules. A client charm (from the 'requires` side of the relation)
that needs to forward alert rules to Loki should place them in a directory named `loki_alert_rules`
within the client charm's source directory (`./src`).

A new Loki configuration is generated every time a new relation is created, or an existing one changes.

The library `log_proxy` provides a way to setup a charms as a Log Proxy (Provider or Consumer) to Loki.

### Libraries

#### `loki_push_api`

This library provides two main objects:

- `LokiPushApiProvider`: This object is meant to be used by any charmed operator that needs to
implement the provider side of the `loki_push_api` relation interface.
For instance a Loki charm.

- `LokiPushApiConsumer`: This object is meant to be used by any charmed operator that needs to
send log to Loki by implementing the consumer side of the `loki_push_api` relation interface.
For instance a Promtail or Grafana agent charm that needs to send logs to Loki.

Learn more about this library [on charmhub](https://charmhub.io/loki-k8s/libraries/loki_push_api).


#### `log_proxy`

This library provides two main objects:

- `LogProxyProvider`: This object can be used by any charmed operator that needs to act
as a Log Proxy to Loki by implementing the provider side of `loki_push_api` relation interface.
For instance a Grafana agent or Promtail charmed operator that receives logs from a workload
and forward them to Loki.

- `LogProxyConsumer`: This object can be used by any K8s charmed operator that needs to
send log to Loki through a Log Proxy by implementing the consumer side of the `loki_push_api`
relation interface.
When a relation with a Charmed Operator that implements the `LogProxyProvider` is established,
this object injects and configure into the workload container a [Promtail binary](https://grafana.com/docs/loki/latest/clients/promtail/)
that will send logs to Loki through a Log Proxy charmed operator.



Filtering logs in Loki is largely performed on the basis of labels.
In the Juju ecosystem, Juju topology labels are used to uniquely identify the workload that
generates telemetry like logs.
In order to be able to control the labels on the logs pushed this object injects a Pebble layer
that runs Promtail in the workload container, injecting Juju topology labels into the
logs on the fly.


Learn more about this library [on charmhub](https://charmhub.io/loki-k8s/libraries/log_proxy).


#### Integration example.


With both libraries `loki_push_api` and `log_proxy` the following integration can be done:


```
┌──────────────────┐  Workload logs  ┌────────────────────┐  Workloads logs ┌──────────────────┐
│                  │ ───────────────►│                    │ ───────────────►│                  │
│ Custom Workload  │                 │  Grafana agent     │                 │ Loki             │
│                  ├─────────────────┤                    ├─────────────────┤                  │
│ Charmed Operator │ loki_push_api   │  Charmed Operator  │  loki_push_api  │ Charmed Operator │
│                  │                 │                    │                 │                  │
└──────────────────┘                 └────────────────────┘                 └──────────────────┘
Uses:                                 Uses:                                  Uses:
- LogProxyConsumer                    - LokiPushApiConsumer                 - LokiPushApiProvider
                                      - LogProxyProvider
```



### Loki charmed Operator Integrations

1. Loki integrates with
[Grafana](https://charmhub.io/grafana-k8s) which provides a dashboard
for viewing logs aggregated by Loki. These dasboards may be
customised by charms that relate to Grafana.

2. Loki forwards alerts to one or more
[Alertmanagers](https://charmhub.io/alertmanager-k8s) that are related
to it.
