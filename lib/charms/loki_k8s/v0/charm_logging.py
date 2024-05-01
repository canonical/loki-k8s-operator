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

import functools
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import (
    Callable,
    Optional,
    Type,
    TypeVar,
    Union,
)

import logging_loki
from ops.charm import CharmBase
from ops.framework import Framework

# The unique Charmhub library identifier, never change it
LIBID = "52ee6051f4e54aedaa60aa04134d1a6d"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = ["python-logging-loki=0.3.1"]

logger = logging.getLogger("charm_logging")

_GetterType = Union[Callable[[CharmBase], Optional[str]], property]

CHARM_LOGGING_ENABLED = "CHARM_LOGGING_ENABLED"


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

        if server_cert:
            # todo figure out how to use cert with this
            logger.warning("server-cert authentication not implemented.")

        root_logger = logging.getLogger()

        for url in logging_endpoints:
            handler = logging_loki.LokiHandler(
                url=url,
                tags=juju_topology,
                # auth=("username", "password"),
                version="1",
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
