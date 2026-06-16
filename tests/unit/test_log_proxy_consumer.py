# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

# Deprecated: This test module covers LogProxyConsumer, which relies on Promtail.
# Promtail is deprecated by Grafana. New integrations should use LokiPushApiConsumer
# with OpenTelemetry Collector instead of LogProxyConsumer.

import json
import os
import platform
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import mock_open, patch
from urllib.error import HTTPError, URLError

import pytest
from charms.loki_k8s.v0 import loki_push_api
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.model import Container as OpsContainer
from ops.pebble import PathError
from ops.testing import Context
from scenario import Container, Model, Relation, Resource, State

LOG_FILES = ["/var/log/apache2/access.log", "/var/log/alternatives.log", "/var/log/test.log"]

HTTP_LISTEN_PORT = 9080
GRPC_LISTEN_PORT = 9095

CONFIG = {
    "clients": [{"url": "http://10.20.30.1:3500/loki/api/v1/push"}],
    "server": {"http_listen_port": HTTP_LISTEN_PORT, "grpc_listen_port": GRPC_LISTEN_PORT},
    "positions": {"filename": "/opt/promtail/positions.yaml"},
    "scrape_configs": [
        {
            "job_name": "system",
            "static_configs": [
                {
                    "targets": ["localhost"],
                    "labels": {
                        "job": "juju_MODEL_20ce829_loki-k8s",
                        "__path__": "/var/log/apache2/access.log",
                    },
                },
                {
                    "targets": ["localhost"],
                    "labels": {
                        "job": "juju_MODEL_20ce829_loki-k8s",
                        "__path__": "/var/log/alternatives.log",
                    },
                },
                {
                    "targets": ["localhost"],
                    "labels": {
                        "job": "juju_MODEL_20ce829_loki-k8s",
                        "__path__": "/var/log/test.log",
                    },
                },
            ],
        }
    ],
}

PROMTAIL_INFO = {
    "filename": "promtail-linux-amd64",
    "zipsha": "978391a174e71cfef444ab9dc012f95d5d7eae0d682eaf1da2ea18f793452031",
    "binsha": "00ed6a4b899698abc97d471c483a6a7e7c95e761714f872eb8d6ffd45f3d32e6",
}
WORKLOAD_BINARY_DIR = "/opt/promtail"
WORKLOAD_POSITIONS_PATH = "{}/positions.yaml".format(WORKLOAD_BINARY_DIR)


class ConsumerCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self._stored.set_default(invalid_events=0)
        self.log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=True
        )

        self.framework.observe(
            self.log_proxy.on.promtail_digest_error, self._register_promtail_error
        )

    def _register_promtail_error(self, _):
        self._stored.invalid_events += 1


class ConsumerCharmSyslogDisabled(ConsumerCharm):
    def __init__(self, *args, **kwargs):
        super(ConsumerCharm, self).__init__(*args)
        self._port = 3100
        self.log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=False
        )


CONSUMER_META = {
    "name": "loki-k8s",
    "containers": {
        "loki": {"resource": "loki-image"},
        "promtail": {"resource": "promtail-image"},
    },
    "requires": {
        "log-proxy": {"interface": "loki_push_api", "optional": True},
    },
}


@pytest.fixture
def consumer_context():
    return Context(ConsumerCharm, meta=CONSUMER_META)


@pytest.fixture
def loki_container():
    return Container("loki", can_connect=True)


@pytest.fixture
def promtail_container():
    return Container("promtail", can_connect=True)


def test_cli_args_with_config_file_parameter(consumer_context, loki_container, promtail_container):
    """Test that CLI args contain config file parameter."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        assert "-config.file=" in charm.log_proxy._cli_args


def test_config_sections_match_expected(consumer_context, loki_container, promtail_container):
    """Test that config has expected sections."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        expected_sections = {"clients", "positions", "scrape_configs", "server"}
        assert set(charm.log_proxy._promtail_config) == expected_sections


def test_config_jobs_match_expected(consumer_context, loki_container, promtail_container):
    """Test that config jobs match expected."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        expected_jobs = {"system", "syslog"}
        assert {x["job_name"] for x in charm.log_proxy._promtail_config["scrape_configs"]} == expected_jobs


def test_config_labels_match_expected(consumer_context, loki_container, promtail_container):
    """Test that config labels match expected."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        for job in charm.log_proxy._promtail_config["scrape_configs"]:
            if job["job_name"] == "system":
                expected = {
                    "__path__",
                    "job",
                    "juju_application",
                    "juju_charm",
                    "juju_unit",
                    "juju_model",
                    "juju_model_uuid",
                }
                for static_config in job["static_configs"]:
                    assert set(static_config["labels"]) == expected


def test_config_syslog_labels_match_expected(consumer_context, loki_container, promtail_container):
    """Test that syslog config labels match expected."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        for job in charm.log_proxy._promtail_config["scrape_configs"]:
            if job["job_name"] == "syslog":
                expected = {
                    "job",
                    "juju_application",
                    "juju_charm",
                    "juju_unit",
                    "juju_model",
                    "juju_model_uuid",
                }
                assert set(job["syslog"]["labels"]) == expected


def test_client_list_matches_expected(consumer_context, loki_container, promtail_container):
    """Test that client list matches expected."""
    log_proxy_rel = Relation(
        "log-proxy",
        remote_app_name="agent",
        remote_units_data={
            0: {"endpoint": json.dumps({"url": "http://10.20.30.1:3500/loki/api/v1/push"})},
            1: {"endpoint": json.dumps({"url": "http://10.20.30.2:3500/loki/api/v1/push"})},
        },
    )

    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        relations=[log_proxy_rel],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.relation_changed(log_proxy_rel), state) as mgr:
        charm = mgr.charm
        expected_clients = {
            "http://10.20.30.1:3500/loki/api/v1/push",
            "http://10.20.30.2:3500/loki/api/v1/push",
        }
        assert {x["url"] for x in charm.log_proxy._clients_list()} == expected_clients


def test_invalid_container_name_fails(consumer_context, loki_container, promtail_container):
    """Test that invalid container name triggers error event."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        charm.log_proxy._get_container("not_present")
        assert charm._stored.invalid_events == 1


def test_valid_container_name_works(consumer_context, loki_container, promtail_container):
    """Test that valid container name returns Container."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        container = charm.log_proxy._get_container("loki")
        assert isinstance(container, OpsContainer)


def test_empty_lookup_with_more_than_one_container_fails(consumer_context, loki_container, promtail_container):
    """Test that empty lookup with multiple containers fails."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        charm.log_proxy._get_container()
        assert charm._stored.invalid_events == 1


def test_sha256sum_is_false_with_file_not_found(consumer_context, loki_container, promtail_container):
    """Test that sha256sum check returns False when file not found."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        mocked = mock_open()
        mocked.side_effect = FileNotFoundError

        with patch("builtins.open", mocked):
            assert charm.log_proxy._sha256sums_matches("file", "foo") is False


@patch("charms.loki_k8s.v0.loki_push_api.BINARY_DIR", mkdtemp(prefix="logproxy-unittest"))
@patch(
    "charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._download_and_push_promtail_to_workload"
)
def test_promtail_sha256sum_mismatch_downloads_new(mock_download, consumer_context, loki_container, promtail_container, caplog):
    """Test that sha256sum mismatch triggers new download."""
    tmpdir = loki_push_api.BINARY_DIR

    # Set up an initial state with a sum that won't match
    fake_promtail = os.path.join(tmpdir, PROMTAIL_INFO["filename"])
    fake_content = "sample_data".encode()
    Path(fake_promtail).write_bytes(fake_content)

    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        charm.log_proxy._obtain_promtail(PROMTAIL_INFO)
        assert "File sha256sum mismatch" in caplog.text
        assert mock_download.called


def test_promtail_can_handle_missing_configuration(consumer_context, loki_container, promtail_container):
    """Test that promtail handles missing configuration gracefully."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        with patch("ops.model.Container.pull") as mock_pull:
            mock_pull.side_effect = PathError("", "irrelevant")
            assert charm.log_proxy._current_config == {}


@patch("charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._is_promtail_installed")
@patch("charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._obtain_promtail")
def test_setup_promtail_handles_url_error_on_download(
    mock_obtain, mock_is_installed, consumer_context, loki_container, promtail_container
):
    # Regression test for https://github.com/canonical/loki-k8s-operator/issues/624
    # GIVEN promtail is not yet installed and the download fails at the connection
    # level (e.g. missing juju proxy configuration), raising a bare URLError
    mock_is_installed.return_value = False
    mock_obtain.side_effect = URLError(reason="[Errno 110] Connection timed out")

    arch = "amd64" if platform.machine() == "x86_64" else platform.machine()
    log_proxy_rel = Relation(
        "log-proxy",
        remote_app_name="agent",
        remote_app_data={
            "promtail_binary_zip_url": json.dumps({arch: {**PROMTAIL_INFO, "url": "http://x"}})
        },
    )
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        relations=[log_proxy_rel],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        # WHEN promtail setup runs
        charm.log_proxy._setup_promtail()
        # THEN the URLError is caught and surfaced as a digest error (hook does not crash)
        assert charm._stored.invalid_events == 1


@patch("charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._is_promtail_installed")
@patch("charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._obtain_promtail")
def test_setup_promtail_handles_http_error_on_download(
    mock_obtain, mock_is_installed, consumer_context, loki_container, promtail_container
):
    # GIVEN promtail is not yet installed and the download fails with an HTTPError
    # (a subclass of URLError), so the previously supported behaviour keeps working
    mock_is_installed.return_value = False
    mock_obtain.side_effect = HTTPError(
        url="http://x", code=404, msg="not found", fp=None, hdrs=None  # type: ignore
    )

    arch = "amd64" if platform.machine() == "x86_64" else platform.machine()
    log_proxy_rel = Relation(
        "log-proxy",
        remote_app_name="agent",
        remote_app_data={
            "promtail_binary_zip_url": json.dumps({arch: {**PROMTAIL_INFO, "url": "http://x"}})
        },
    )
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        relations=[log_proxy_rel],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_context(consumer_context.on.start(), state) as mgr:
        charm = mgr.charm
        # WHEN promtail setup runs
        charm.log_proxy._setup_promtail()
        # THEN the HTTPError is caught and surfaced as a digest error (hook does not crash)
        assert charm._stored.invalid_events == 1


# --- TestLogProxyConsumerWithoutSyslog ---


@pytest.fixture
def consumer_no_syslog_context():
    return Context(ConsumerCharmSyslogDisabled, meta=CONSUMER_META)


def test_syslog_not_enabled(consumer_no_syslog_context, loki_container, promtail_container):
    """Test that syslog is not in config when disabled."""
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_no_syslog_context(consumer_no_syslog_context.on.start(), state) as mgr:
        charm = mgr.charm
        assert "syslog" not in {x["job_name"] for x in charm.log_proxy._promtail_config["scrape_configs"]}


# --- TestLogProxyConsumerWithPromtailResource ---


class ConsumerCharmWithPromtailResource(CharmBase):
    _stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._port = 3100
        self._stored.set_default(invalid_events=0)
        self.log_proxy = LogProxyConsumer(
            charm=self, container_name="loki", log_files=LOG_FILES, enable_syslog=True
        )


CONSUMER_WITH_RESOURCE_META = {
    "name": "loki-k8s",
    "containers": {
        "loki": {"resource": "loki-image"},
        "promtail": {"resource": "promtail-image"},
    },
    "requires": {
        "log-proxy": {"interface": "loki_push_api", "optional": True},
    },
    "resources": {
        "promtail-bin": {"type": "file", "description": "promtail binary", "filename": "promtail-linux-amd64"},
    },
}


@pytest.fixture
def consumer_with_resource_context():
    return Context(ConsumerCharmWithPromtailResource, meta=CONSUMER_WITH_RESOURCE_META)


def test_fetch_promtail_from_attached_resource(
    consumer_with_resource_context, loki_container, promtail_container, caplog, tmp_path
):
    """Scenario: the promtail binary is provided via an attached juju resource.

    Note: the original Harness test also asserted ``_promtail_attached_as_resource``
    is False before attaching. Scenario requires every *declared* resource to be
    present in ``State.resources`` (a missing one raises ``RuntimeError``, not the
    ``ModelError`` the lib catches), so the "declared but unattached" state is not
    representable here; we exercise the attached path, which is the feature itself.
    """
    # GIVEN the "promtail-bin" resource (hardcoded name in the lib) is attached
    resource_file = tmp_path / PROMTAIL_INFO["filename"]
    resource_file.write_text("somecontent")
    state = State(
        leader=True,
        containers=[loki_container, promtail_container],
        resources=[Resource(name="promtail-bin", path=resource_file)],
        model=Model(name="MODEL", uuid="20ce8299-3634-4bef-8bd8-5ace6c8816b4"),
    )

    with consumer_with_resource_context(
        consumer_with_resource_context.on.start(), state
    ) as mgr:
        charm = mgr.charm
        # THEN the lib detects the attached resource
        assert charm.log_proxy._promtail_attached_as_resource is True

        # AND pushing it to the workload reports it came from a resource
        binary_path = os.path.join("/tmp", PROMTAIL_INFO["filename"])
        with caplog.at_level("INFO", logger="charms.loki_k8s.v0.loki_push_api"):
            assert charm.log_proxy._push_promtail_if_attached(binary_path) is True
        assert (
            "Promtail binary file has been obtained from an attached resource." in caplog.text
        )


# --- TestTypeValidation ---


def charm_factory(log_files):
    """Factory to create consumer charm with specific log_files."""
    class TypeValidationConsumerCharm(CharmBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self.loki_consumer = LogProxyConsumer(self, log_files=log_files)

    return TypeValidationConsumerCharm


TYPE_VALIDATION_META = {
    "name": "loki-k8s",
    "containers": {"app": {"resource": "app-image"}},
    "requires": {"log-proxy": {"interface": "loki_push_api"}},
}


@pytest.mark.parametrize(
    "log_files",
    [
        "",
        None,
        [],
        "/my/file.log",
        ["/my/file.log"],
    ],
)
def test_log_files_various_valid_types(log_files):
    """Test that various valid log_files types work."""
    charm_class = charm_factory(log_files)
    ctx = Context(charm_class, meta=TYPE_VALIDATION_META)
    container = Container("app", can_connect=True)
    state = State(containers=[container])

    # Should not raise
    ctx.run(ctx.on.start(), state)


@pytest.mark.parametrize(
    "log_files",
    [
        {"/my/file.log"},
        ("/my/file.log",),
    ],
)
def test_log_files_various_invalid_types(log_files):
    """Test that various invalid log_files types raise TypeError."""
    charm_class = charm_factory(log_files)
    ctx = Context(charm_class, meta=TYPE_VALIDATION_META)
    container = Container("app", can_connect=True)
    state = State(containers=[container])

    with pytest.raises(Exception):  # Scenario wraps the TypeError
        ctx.run(ctx.on.start(), state)
