output "app_name" {
  value = juju_application.loki.name
}

output "endpoints" {
  value = {
    # Requires

    alertmanager          = "alertmanager"
    ingress               = "ingress"
    catalogue             = "catalogue"
    certificates          = "certificates"
    charm_tracing         = "charm-tracing"
    workload_tracing      = "workload-tracing"

    # Provides

    metrics_endpoint = "metrics-endpoint"
    grafana_source        = "grafana-source"
    grafana_dashboard     = "grafana-dashboard"
    receive_remote_write  = "receive-remote-write"
    send_datasource       = "send-datasource"
    logging               = "logging"
  }
}
