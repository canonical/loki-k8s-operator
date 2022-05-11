# loki-tester

## Description

This charm generates synthetic logs that may be used by the Loki
Operator and used for the purposes of integration testing the
Loki operator. The synthetic data is actually this charm's own
Python debug logs.

## Usage

Build the Loki Tester charm using `charmcraft pack` in the
`tests/integration/loki-tester` directory.

Deploy the Loki charm and Loki Tester charm and add a relation
between them.

```
juju deploy loki-k8s --channel=beta
juju deploy ./loki-tester_ubuntu-20.04-amd64.charm
juju relate loki-k8s loki-tester
```

Query logs sent by Loki tester to Loki
```
curl -G -s http://$(lokiaddr):3100/loki/api/v1/query_range --data-urlencode "query={logger=\"Loki-Tester\"}"
```
Note `$(lokiaddr)` is the IP address of the deployed Loki application.

Query the alert rules sent by the Loki tester to Loki
```
curl -G -s http://$(lokiaddr):3100/prometheus/api/v1/rules
```

Make Loki tester send an error log
```
juju run-action loki-tester/0 log-error message="some error message"
```

Check a if the `log-error` action is triggering an alert by querrying
the alerts raised by Loki.
```
curl -G -s http://$(lokiaddr):3100/prometheus/api/v1/alerts
```
You may need to run this a couple of times before you see the alert because
there is a time lag between running the action and the alert triggering.
