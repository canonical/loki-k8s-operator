#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This charm library contains utilities to automatically forward your charm logs to a loki-push-api endpoint.

(yes! charm code, not workload code!)

This means that, if your charm is related to, for example, COS' Loki charm (or a Grafana Agent),
you will be able to inspect in real time from the Grafana dashboard the logs emitted by your charm.

To start using this library, you need to do two things:
1) decorate your charm class with

`@log_charm(loki_push_api_endpoint="my_logging_endpoint")`

2) add to your charm a "my_logging_endpoint" (you can name this attribute whatever you like) **property**
that returns an http/https endpoint url. If you are using the `LogProxyConsumer` as
`self.logging = LogProxyConsumer(self, ...)`, the implementation could be:

```
    @property
    def my_logging_endpoint(self) -> List[str]:
        '''Loki push API endpoints for charm logging'''
        return self.logging.loki_endpoints:
```

The ``log_charm`` decorator will take these endpoints and set up the root logger (as in python's
logging module root logger) to forward all logs to these loki endpoints.

3) If you were passing a certificate using `server_cert`, you need to change it to provide an *absolute* path to
the certificate file.
"""
import copy
import functools
import logging
import os
import string
import time
from contextlib import contextmanager
from logging.config import ConvertingDict
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import requests
from ops.charm import CharmBase
from ops.framework import Framework

# prevent infinite recursion because on failure urllib3 will push more logs
# https://github.com/GreyZmeem/python-logging-loki/issues/18
logging.getLogger("urllib3").setLevel(logging.INFO)

# The unique Charmhub library identifier, never change it
LIBID = "52ee6051f4e54aedaa60aa04134d1a6d"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = []

logger = logging.getLogger("charm_logging")
_GetterType = Union[Callable[[CharmBase], Optional[str]], property]
CHARM_LOGGING_ENABLED = "CHARM_LOGGING_ENABLED"


# from https://github.com/GreyZmeem/python-logging-loki, which seems to be dead
class LokiEmitter:
    """Base Loki emitter class."""

    #: Success HTTP status code from Loki API.
    success_response_code: int = 204

    #: Label name indicating logging level.
    level_tag: str = "severity"
    #: Label name indicating logger name.
    logger_tag: str = "logger"

    #: String contains chars that can be used in label names in LogQL.
    label_allowed_chars: str = "".join((string.ascii_letters, string.digits, "_"))
    #: A list of pairs of characters to replace in the label name.
    label_replace_with: Tuple[Tuple[str, str], ...] = (
        ("'", ""),
        ('"', ""),
        (" ", "_"),
        (".", "_"),
        ("-", "_"),
    )

    def __init__(self, url: str, tags: Optional[dict] = None, cert: Optional[str] = None):
        """Create new Loki emitter.

        Arguments:
            url: Endpoint used to send log entries to Loki (e.g. `https://my-loki-instance/loki/api/v1/push`).
            tags: Default tags added to every log record.
            cert: Absolute path to a ca cert for TLS authentication.

        """
        #: Tags that will be added to all records handled by this handler.
        self.tags = tags or {}
        #: Loki JSON push endpoint (e.g `http://127.0.0.1/loki/api/v1/push`)
        self.url = url
        #: Optional cert for TLS auth
        self.cert = cert

        self._session: Optional[requests.Session] = None

    def __call__(self, record: logging.LogRecord, line: str):
        """Send log record to Loki."""
        payload = self.build_payload(record, line)
        resp = self.session.post(self.url, json=payload, timeout=5)
        if resp.status_code != self.success_response_code:
            raise ValueError(
                "Unexpected Loki API response status code: {0}".format(resp.status_code)
            )

    def build_payload(self, record: logging.LogRecord, line) -> dict:
        """Build JSON payload with a log entry."""
        labels = self.build_tags(record)
        ns = 1e9
        ts = str(int(time.time() * ns))
        stream = {
            "stream": labels,
            "values": [[ts, line]],
        }
        return {"streams": [stream]}

    @property
    def session(self) -> requests.Session:
        """Create HTTP(s) session."""
        if self._session is None:
            self._session = requests.Session()
            # very unclear why we don't need to use 'Session.cert' for this, but...
            # See: https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification
            self._session.verify = self.cert or None
        return self._session

    def close(self):
        """Close HTTP session."""
        if self._session is not None:
            self._session.close()
            self._session = None

    @functools.lru_cache(256)
    def format_label(self, label: str) -> str:
        """Build label to match prometheus format.

        `Label format <https://prometheus.io/docs/concepts/data_model/#metric-names-and-labels>`_
        """
        for char_from, char_to in self.label_replace_with:
            label = label.replace(char_from, char_to)
        return "".join(char for char in label if char in self.label_allowed_chars)

    def build_tags(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Return tags that must be send to Loki with a log record."""
        tags = dict(self.tags) if isinstance(self.tags, ConvertingDict) else self.tags
        tags = copy.deepcopy(tags)
        tags[self.level_tag] = record.levelname.lower()
        tags[self.logger_tag] = record.name

        extra_tags = getattr(record, "tags", {})
        if not isinstance(extra_tags, dict):
            return tags

        for tag_name, tag_value in extra_tags.items():
            cleared_name = self.format_label(tag_name)
            if cleared_name:
                tags[cleared_name] = tag_value

        return tags


class LokiHandler(logging.Handler):
    """Log handler that sends log records to Loki.

    `Loki API <https://github.com/grafana/loki/blob/master/docs/api.md>`_
    """

    def __init__(
        self,
        url: str,
        tags: Optional[dict] = None,
        # username, password tuple
        cert: Optional[str] = None,
    ):
        """Create new Loki logging handler.

        Arguments:
            url: Endpoint used to send log entries to Loki (e.g. `https://my-loki-instance/loki/api/v1/push`).
            tags: Default tags added to every log record.

            # FIXME: Session expects a .pem file it says
            cert: Optional absolute path to cert file for TLS auth.

        """
        super().__init__()
        self.emitter = LokiEmitter(url, tags, cert)

    def handleError(self, record):  # noqa: N802
        """Close emitter and let default handler take actions on error."""
        self.emitter.close()
        super().handleError(record)

    def emit(self, record: logging.LogRecord):
        """Send log record to Loki."""
        # noinspection PyBroadException
        try:
            self.emitter(record, self.format(record))
        except Exception:
            self.handleError(record)


def is_enabled() -> bool:
    """Whether charm logging is enabled."""
    return os.getenv(CHARM_LOGGING_ENABLED, "1") == "1"


class CharmLoggingError(Exception):
    """Base class for all exceptions raised by this module."""


class InvalidEndpointError(CharmLoggingError):
    """Raised if an endpoint is invalid."""


@contextmanager
def charm_logging_disabled():
    """Contextmanager to temporarily disable charm logging.

    For usage in tests.
    """
    previous = os.getenv(CHARM_LOGGING_ENABLED, "1")
    os.environ[CHARM_LOGGING_ENABLED] = "0"
    yield
    os.environ[CHARM_LOGGING_ENABLED] = previous


_C = TypeVar("_C", bound=Type[CharmBase])
_T = TypeVar("_T", bound=type)
_F = TypeVar("_F", bound=Type[Callable])


def _get_logging_endpoints(logging_endpoints_getter, self, charm):
    if isinstance(logging_endpoints_getter, property):
        logging_endpoints = logging_endpoints_getter.__get__(self)
    else:  # method or callable
        logging_endpoints = logging_endpoints_getter(self)

    if logging_endpoints is None:
        logger.debug(
            f"{charm}.{logging_endpoints_getter} returned None; quietly disabling "
            f"charm_logging for the run."
        )
        return None

    errors = []
    logging_endpoints = tuple(logging_endpoints)
    sanitized_logging_endponts = []
    for endpoint in logging_endpoints:
        if isinstance(endpoint, str):
            sanitized_logging_endponts.append(endpoint)
        else:
            errors.append(endpoint)

    if errors:
        if sanitized_logging_endponts:
            logger.error(
                f"{charm}.{logging_endpoints_getter} returned some invalid endpoint strings: {errors}"
            )
        else:
            logger.error(
                f"{charm}.{logging_endpoints_getter} should return an iterable of Loki push-api (compatible) endpoints (strings); "
                f"got {errors} instead."
            )

    return sanitized_logging_endponts


def _get_server_cert(server_cert_getter, self, charm):
    if isinstance(server_cert_getter, property):
        server_cert = server_cert_getter.__get__(self)
    else:  # method or callable
        server_cert = server_cert_getter(self)

    if server_cert is None:
        logger.warning(
            f"{charm}.{server_cert_getter} returned None; sending logs over INSECURE connection."
        )
        return None
    if not Path(server_cert).is_absolute():
        raise ValueError(
            f"{charm}.{server_cert_getter} should return a valid tls cert absolute path (string | Path)); "
            f"got {server_cert} instead."
        )
    return server_cert


def _setup_root_logger_initializer(
    charm: Type[CharmBase],
    logging_endpoints_getter: _GetterType,
    server_cert_getter: Optional[_GetterType],
    service_name: Optional[str] = None,
):
    """Patch the charm's initializer."""
    original_init = charm.__init__

    @functools.wraps(original_init)
    def wrap_init(self: CharmBase, framework: Framework, *args, **kwargs):
        original_init(self, framework, *args, **kwargs)

        if not is_enabled():
            logger.info("Charm logging DISABLED by env: skipping root logger initialization")
            return

        try:
            logging_endpoints = _get_logging_endpoints(logging_endpoints_getter, self, charm)
        except Exception:
            # if anything goes wrong with retrieving the endpoint, we go on with logging disabled.
            # better than breaking the charm.
            logger.exception(
                f"exception retrieving the logging "
                f"endpoint from {charm}.{logging_endpoints_getter}; "
                f"proceeding with charm_logging DISABLED. "
            )
            return

        if not logging_endpoints:
            return

        juju_topology = {
            "juju_unit": self.unit.name,
            "juju_application": self.app.name,
            "juju_model": self.model.name,
            "juju_model_uuid": self.model.uuid,
            "service_name": service_name or self.app.name,
            "charm_type_name": type(self).__name__,
            "dispatch_path": os.getenv("JUJU_DISPATCH_PATH", ""),
        }
        server_cert: Optional[Union[str, Path]] = (
            _get_server_cert(server_cert_getter, self, charm) if server_cert_getter else None
        )

        root_logger = logging.getLogger()

        for url in logging_endpoints:
            handler = LokiHandler(
                url=url,
                tags=juju_topology,
                cert=server_cert,
                # auth=("username", "password"),
            )

            root_logger.addHandler(handler)
            root_logger.debug(
                "Initialized charm logger",
                extra={"tags": {"endpoint": url}},
            )
        return

    charm.__init__ = wrap_init


def log_charm(
    logging_endpoints: str,
    server_cert: Optional[str] = None,
    service_name: Optional[str] = None,
):
    """Set up the root logger to forward any charm logs to one or more Loki push API endpoints.

    Usage:
    >>> from charms.loki_k8s.v0.charm_logging import log_charm
    >>> from charms.loki_k8s.v1.loki_push_api import LogProxyConsumer
    >>> from ops import CharmBase
    >>>
    >>> @log_charm(
    >>>         logging_endpoints="loki_push_api_urls",
    >>> )
    >>> class MyCharm(CharmBase):
    >>>
    >>>     def __init__(self, framework: Framework):
    >>>         ...
    >>>         self.logging = LogProxyConsumer(self, ...)
    >>>
    >>>     @property
    >>>     def loki_push_api_urls(self) -> Optional[List[str]]:
    >>>         return [endpoint['url'] for endpoint in self.logging.loki_endpoints]
    >>>
    :param server_cert: method or property on the charm type that returns an
        optional absolute path to a tls certificate to be used when sending traces to a remote server.
        If it returns None, an _insecure_ connection will be used.
    :param logging_endpoints: name of a property on the charm type that returns a sequence
        of (fully resolvable) Loki push API urls. If None, charm logging will be effectively disabled.
        Else, the root logger will be set up to forward all logs to those endpoints.
    :param service_name: service name tag to attach to all logs generated by this charm.
        Defaults to the juju application name this charm is deployed under.
    """

    def _decorator(charm_type: Type[CharmBase]):
        """Autoinstrument the wrapped charmbase type."""
        _autoinstrument(
            charm_type,
            logging_endpoints_getter=getattr(charm_type, logging_endpoints),
            server_cert_getter=getattr(charm_type, server_cert) if server_cert else None,
            service_name=service_name,
        )
        return charm_type

    return _decorator


def _autoinstrument(
    charm_type: Type[CharmBase],
    logging_endpoints_getter: _GetterType,
    server_cert_getter: Optional[_GetterType] = None,
    service_name: Optional[str] = None,
) -> Type[CharmBase]:
    """Set up logging on this charm class.

    Use this function to get out-of-the-box traces for all events emitted on this charm and all
    method calls on instances of this class.

    Usage:

    >>> from charms.loki_k8s.v0.charm_logging import _autoinstrument
    >>> from ops.main import main
    >>> _autoinstrument(
    >>>         MyCharm,
    >>>         logging_endpoints_getter=MyCharm.get_loki_endpoints,
    >>>         service_name="MyCharm",
    >>> )
    >>> main(MyCharm)

    :param charm_type: the CharmBase subclass to autoinstrument.
    :param server_cert_getter: method or property on the charm type that returns an
        optional absolute path to a tls certificate to be used when sending traces to a remote server.
        If it returns None, an _insecure_ connection will be used.
    :param logging_endpoints_getter: name of a property on the charm type that returns a sequence
        of (fully resolvable) Loki push API urls. If None, charm logging will be effectively disabled.
        Else, the root logger will be set up to forward all logs to those endpoints.
    :param service_name: service name tag to attach to all logs generated by this charm.
        Defaults to the juju application name this charm is deployed under.
    """
    logger.info(f"instrumenting {charm_type}")
    _setup_root_logger_initializer(
        charm_type,
        logging_endpoints_getter,
        server_cert_getter=server_cert_getter,
        service_name=service_name,
    )
    return charm_type
