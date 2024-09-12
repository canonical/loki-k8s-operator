from unittest.mock import MagicMock

import pytest
from charms.loki_k8s.v1.loki_push_api import LokiPushApiError, charm_logging_config


def test_charm_logging_config_http():
    # GIVEN endpoints are http
    raw_eps = ["http://foo.com", "http://woo.com"]
    eps = [{"url": url} for url in raw_eps]

    lpa = MagicMock()
    lpa.loki_endpoints = eps
    # AND we don't have a cert (tls not supported)
    endpoints, cert = charm_logging_config(lpa, None)

    # enable charm logging (http)
    assert endpoints == raw_eps
    assert cert is None


def test_charm_logging_config_https_tls_ready(tmp_path):
    # GIVEN endpoints are https
    raw_eps = ["https://foo.com", "https://woo.com"]
    eps = [{"url": url} for url in raw_eps]
    cert_path = tmp_path / "foo.crt"
    # AND cert file exists
    cert_path.write_text("hello cert")

    lpa = MagicMock()
    lpa.loki_endpoints = eps
    endpoints, cert = charm_logging_config(lpa, cert_path)

    # enable charm logging (https)
    assert endpoints == raw_eps
    assert cert == str(cert_path)


def test_charm_logging_config_https_tls_not_ready(tmp_path):
    # GIVEN endpoints are https
    raw_eps = ["https://foo.com", "https://woo.com"]
    eps = [{"url": url} for url in raw_eps]
    # BUT cert file does not exist
    cert_path = tmp_path / "foo.crt"

    lpa = MagicMock()
    lpa.loki_endpoints = eps
    endpoints, cert = charm_logging_config(lpa, cert_path)

    # disable charm logging
    assert endpoints is None
    assert cert is None


def test_charm_logging_config_https_tls_not_impl(tmp_path):
    # GIVEN endpoints are https
    raw_eps = ["https://foo.com", "https://woo.com"]
    eps = [{"url": url} for url in raw_eps]
    # AND we don't even pretend there's a cert

    lpa = MagicMock()
    lpa.loki_endpoints = eps
    with pytest.raises(LokiPushApiError):
        charm_logging_config(lpa, None)


def test_charm_logging_config_https_http_mix(tmp_path):
    # GIVEN endpoints are a mix of http and https
    raw_eps = ["https://foo.com", "http://woo.com"]
    eps = [{"url": url} for url in raw_eps]
    lpa = MagicMock()
    lpa.loki_endpoints = eps

    # we get an error whether we pass a cert or not
    with pytest.raises(LokiPushApiError):
        charm_logging_config(lpa, "/foo/bar.crt")

    with pytest.raises(LokiPushApiError):
        charm_logging_config(lpa, None)
