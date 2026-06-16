# Prometheus Alert Rule Tests

This directory contains unit tests for Prometheus alert rules.

## Running the tests

You need `promtool` to run these tests. You can download it from the [Prometheus releases page](https://github.com/prometheus/prometheus/releases).

```bash
# Download and install promtool (example for Linux AMD64)
curl -LO https://github.com/prometheus/prometheus/releases/download/v2.54.1/prometheus-2.54.1.linux-amd64.tar.gz
tar xzf prometheus-2.54.1.linux-amd64.tar.gz
sudo cp prometheus-2.54.1.linux-amd64/promtool /usr/local/bin/

# Run a specific test file
promtool test rules tests/prometheus_alert_rules/test_loki_request_latency.yaml

# Run all tests
promtool test rules tests/prometheus_alert_rules/*.yaml
```

## Test files

- `test_loki_request_latency.yaml` - Tests for the LokiRequestLatency alert rule
- `test_loki_distributor_failures.yaml` - Tests for the LokiDistributorRejectingLogs alert rule

## Test coverage

The tests verify that:
1. Alerts fire when conditions are met
2. Alerts don't fire when conditions are not met
3. Alerts aggregate by the correct labels (namespace, job, route)
4. Alerts respect the `for` duration before firing
5. Filters (e.g., excluding tail routes) work correctly
