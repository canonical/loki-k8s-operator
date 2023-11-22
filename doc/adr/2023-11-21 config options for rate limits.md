# Charm config options for ingestion rate limits

## Context and Problem Statement
The default ingestion rate limits for Loki result in resource utilization capped at ~30%
of a 8cpu16gb VM. Juju admins should have a way for configuring the rate limits to allow
for higher resource utilization.

## Considered Options

- Add individual config options on a per-need basis
- Config overlay option (deep merge)
- Juju feature request for nested config options

## Decision Outcome

Chosen option: "Add individual config options on a per-need basis", because we value UX over versatility.

### Consequences

* Good, because config options are easy to use.
* Good, because involves a maintainable, small volume of changes.
* Bad, because does not fully address the inherent versatility of Loki config.

## Pros and Cons of the Options

### Add individual config options on a per-need basis

* Good, because config options are easy to use.
* Good, because involves a maintainable, small volume of changes.
* Bad, because does not fully address the inherent versatility of Loki config.

### Config overlay option (deep merge)

* Good, because would have a very small code change.
* Good, because offers the Juju admin the full versatility of Loki config.
* Bad, because config option would be not as easy to use.
* Bad, because user-set values may result in undesired overrides of charm options (and 
  we do not want to manage an exclude-/allow-list).

### Juju feature request for nested config options
* Good, because we could mirror the entire Loki config as (nested) charm options.
* Bad, because we would need to maintain a "schema" compatibility with Loki.
* Bad, because charm revision may become coupled to workload version.
* Bad, because the feature request is likely to be rejected.

## More Information
- https://juju.is/docs/sdk/config-yaml#heading--options
- https://grafana.com/docs/loki/latest/configure/#limits_config
