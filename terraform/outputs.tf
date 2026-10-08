output "app_name" {
  value = juju_application.loki.name
}

output "provides" {
  value = {
    metrics_endpoint     = "metrics-endpoint"
    grafana_source       = "grafana-source"
    grafana_dashboard    = "grafana-dashboard"
    receive_remote_write = "receive-remote-write"
    send_datasource      = "send-datasource"
    logging              = "logging"
  }
}

output "requires" {
  value = {
    alertmanager      = "alertmanager"
    send_remote_write = "send-remote-write"
    ingress           = "ingress"
    catalogue         = "catalogue"
    certificates      = "certificates"
    charm_tracing     = "charm-tracing"
    workload_tracing  = "workload-tracing"
  }
}
