## Integrating Loki Charmed Operator

### Overview

This Loki Charmed Operator provides two libraries for integrating with other charms:

- [`loki_push_api`](https://charmhub.io/loki-k8s/libraries/loki_push_api)
- [`log_proxy`](https://charmhub.io/loki-k8s/libraries/log_proxy)


The `loki_push_api` library provides an endpoint URL used to send log entries to Loki from [Loki clients](https://grafana.com/docs/loki/latest/clients/).
You can read more about this in [Loki documentation page.](https://grafana.com/docs/loki/latest/api/#post-lokiapiv1push)

The Loki charm supports user-provided alert rules. A client charm (from the 'requires` side of the relation)
that needs to forward alert rules to Loki should place them in a directory named `loki_alert_rules`
within the client charm's source directory (`./src`).

A new Loki configuration is generated every time a new relation is created, or an existing one changes.

The library `log_proxy` provides a way to setup a charms as a Log Proxy (Provider or Consumer) to Loki.

### Libraries

#### `loki_push_api`

This library provides two main objects:

- `LokiPushApiProvider`: This object may be used by any charmed operator that wants to
provide a way to push loki logs **to it**. For instance a Loki charm.

- `LokiPushApiConsumer`: This object may be used by any charmed operator that wants to
send logs to Loki by implementing the consumer side of the `loki_push_api` relation interface.
For instance a Promtail, Grafana agent charm, or any other application charm that wants to be able to send logs to Loki.

Learn more about this library [on charmhub](https://charmhub.io/loki-k8s/libraries/loki_push_api).


#### `log_proxy`

This library provides two main objects:

- `LogProxyProvider`: This object may be used by any charmed operator that wants to act
as a log proxy to Loki by implementing the provider side of the `loki_push_api` relation interface.
For instance, a Grafana agent or Promtail charmed operator receiving logs from a workload
and forwarding them to Loki.

- `LogProxyConsumer`: This object may be used by any K8s charmed operator that wants to
send logs to Loki through a log proxy by implementing the consumer side of the `loki_push_api`
relation interface.
When a relation with a Charmed Operator implementing the `LogProxyProvider` is established,
this object injects a [Promtail binary](https://grafana.com/docs/loki/latest/clients/promtail/) into the workload container. This binary will then send logs to Loki through the log proxy provider.



Filtering logs in Loki is largely performed on the basis of labels.
In the Juju ecosystem, Juju topology labels are used to uniquely identify the workload generating the telemetry (like logs).

In order to be able to control the labels of the logs pushed, this object injects a Pebble layer
for running Promtail into the workload container. Promtail will then inject Juju topology labels into each
log entry on the fly.


Learn more about this library [on charmhub](https://charmhub.io/loki-k8s/libraries/log_proxy).


#### Integration example


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
[Grafana](https://charmhub.io/grafana-k8s), providing a data source
for viewing logs stored by Loki. This data source may then be
consumed in dashboards provided by other charms relating to Grafana.

2. Loki forwards alerts to one or more
[Alertmanagers](https://charmhub.io/alertmanager-k8s) that are related
to it.
