resource "juju_application" "loki" {
  name  = var.app_name
  model = var.model_name

  trust = true # We always need this variable to be true in order to be able to apply resources limits. 

  charm {
    name     = "loki-k8s"
    channel  = var.channel
    revision = var.revision
  }

  units  = var.units
  config = var.config
}