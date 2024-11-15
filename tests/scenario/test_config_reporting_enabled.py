import yaml
from ops.testing import Container, Exec, State, pebble

containers = [
    Container(
        name="loki",
        can_connect=True,
        layers={
            "loki": pebble.Layer(
                {
                    "services": {
                        "loki": {"startup": "enabled"},
                    },
                }
            ),
        },
        execs={Exec(["update-ca-certificates", "--fresh"], return_code=0)},
    ),
    Container(name="node-exporter", can_connect=True),
]


def test_reporting_enabled(context):
    # GIVEN the "reporting_enabled" config option is set to True
    state = State(leader=True, config={"reporting-enabled": True}, containers=containers)

    # WHEN config-changed fires
    out = context.run(context.on.config_changed(), state)

    # THEN the config file is written WITHOUT the [analytics] section being rendered
    simulated_pebble_filesystem = out.get_container("loki").get_filesystem(context)
    grafana_config_path = simulated_pebble_filesystem / "etc/loki/loki-local-config.yaml"

    with open(grafana_config_path, "r") as file:
        config = yaml.safe_load(file)

    assert "analytics" not in config


def test_reporting_disabled(context):
    # GIVEN the "reporting_enabled" config option is set to False
    state = State(leader=True, config={"reporting-enabled": False}, containers=containers)

    # WHEN config-changed fires
    out = context.run(context.on.config_changed(), state)

    # THEN the config file is written WITH the [analytics] section being rendered
    simulated_pebble_filesystem = out.get_container("loki").get_filesystem(context)
    grafana_config_path = simulated_pebble_filesystem / "etc/loki/loki-local-config.yaml"

    with open(grafana_config_path, "r") as file:
        config = yaml.safe_load(file)

    assert "analytics" in config
    assert not config["analytics"].get("reporting_enabled")

    # AND the "loki" service is restarted
    # TODO Does it make sense to check this if the charm under test's lifetime is only for the config-changed?
    # TODO How to assert this?
