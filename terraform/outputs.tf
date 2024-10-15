# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.loki.name
}

# Required integration endpoints

output "alertmanager_endpoint" {
  description = "Name of the endpoint used by Loki to send out the alerts."
  value       = "alertmanager"
}

output "ingress_endpoint" {
  description = "Name of the endpoint used by Loki for the ingress configuration."
  value       = "ingress"
}

output "certificates_endpoint" {
  description = "Name of the endpoint used to integrate with the TLS certificates provider."
  value       = "certificates"
}

output "catalogue_endpoint" {
  description = "Name of the endpoint used by Loki for the Catalogue integration."
  value       = "catalogue"
}

output "tracing_endpoint" {
  description = "Name of the endpoint used by Loki for pushing traces to a tracing endpoint provided by Tempo."
  value       = "tracing"
}

# Provided integration endpoints

output "logging_endpoint" {
  description = "Name of the endpoint used by Loki to accept logs from client applications."
  value       = "logging"
}

output "metrics_endpoint" {
  description = "Exposes the Prometheus metrics endpoint providing telemetry about the Loki instance."
  value       = "metrics-endpoint"
}

output "grafana_dashboard_endpoint" {
  description = "Forwards the built-in Grafana dashboard(s) for monitoring Loki."
  value       = "grafana-dashboard"
}

output "grafana_source_endpoint" {
  description = "Name of the endpoint used by Loki to create a datasource in Grafana."
  value       = "grafana-source"
}
