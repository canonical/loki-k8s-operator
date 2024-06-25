#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""This charm library contains utilities to automatically forward your charm logs to a loki-push-api endpoint.

(yes! charm code, not workload code!)

If your charm isn't already related to Loki using any of the
consumers/forwarders from the ``loki_push_api`` library, you need to:

    charmcraft fetch-lib charms.loki_k8s.v1.loki_push_api

and add the logging consumer that matches your use case.
See https://charmhub.io/loki-k8s/libraries/loki_push_apihttps://charmhub.io/loki-k8s/libraries/loki_push_api
for more information.

Once your charm is related to, for example, COS' Loki charm (or a Grafana Agent),
you will be able to inspect in real time from the Grafana dashboard the logs emitted by your charm.

## Labels

The library will inject the following labels into the records sent to Loki:
- ``model``: name of the juju model this charm is deployed to
- ``model_uuid``: uuid of the model
- ``application``: juju application name (such as 'mycharm')
- ``unit``: unit name (such as 'mycharm/0')
- ``charm_name``: name of the charm (whatever is in metadata.yaml) under 'name'.
- ``juju_hook_name``: name of the juju event being processed
` ``service_name``: name of the service this charm represents.
    Defaults to app name, but can be configured by the user.

## Usage

To start using this library, you need to do two things:
1) decorate your charm class with

    @log_charm(loki_push_api_endpoint="my_logging_endpoints")

2) add to your charm a "my_logging_endpoint" (you can name this attribute whatever you like) **property**
that returns an http/https endpoint url. If you are using the `LokiPushApiConsumer` as
`self.logging = LokiPushApiConsumer(self, ...)`, the implementation could be:

    @property
    def my_logging_endpoints(self) -> List[str]:
        '''Loki push API endpoints for charm logging.'''
        # this will return an empty list if there is no relation or there is no data yet in the relation
        return ["http://loki-0.loki.svc.cluster.local:3100"]

The ``log_charm`` decorator will take these endpoints and set up the root logger (as in python's
logging module root logger) to forward all logs to these loki endpoints.

## TLS support
If your charm integrates with a tls provider which is also trusted by the logs receiver, you can
configure TLS by passing a ``server_cert`` parameter to the decorator.

If you're not using the same CA as the loki-push-api endpoint you are sending logs to,
you'll need to implement a cert-transfer relation to obtain the CA certificate from the same
CA that Loki is using.

```
@log_charm(loki_push_api_endpoint="my_logging_endpoint", server_cert="my_server_cert")
class MyCharm(...):
    ...

    @property
    def my_server_cert(self) -> Optional[str]:
        '''Absolute path to a server crt if TLS is enabled.'''
        if self.tls_is_enabled():
            return "/path/to/my/server_cert.crt"
```
"""
import functools
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import (
    Callable,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

from cosl import JujuTopology
from cosl.loki_logger import LokiHandler  # pyright:ignore[reportMissingImports]
from ops.charm import CharmBase
from ops.framework import Framework

# The unique Charmhub library identifier, never change it
LIBID = "52ee6051f4e54aedaa60aa04134d1a6d"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2

PYDEPS = ["cosl"]

logger = logging.getLogger("charm_logging")
_EndpointGetterType = Union[Callable[[CharmBase], Optional[Sequence[str]]], property]
_CertGetterType = Union[Callable[[CharmBase], Optional[str]], property]
CHARM_LOGGING_ENABLED = "CHARM_LOGGING_ENABLED"


def is_enabled() -> bool:
    """Whether charm logging is enabled.

    We assume it is enabled, unless the envvar CHARM_LOGGING_ENABLED is set to `0`
    (or anything except `1`).
    """
    return os.getenv(CHARM_LOGGING_ENABLED, "1") == "1"


class CharmLoggingError(Exception):
    """Base class for all exceptions raised by this module."""


class InvalidEndpointError(CharmLoggingError):
    """Raised if an endpoint is invalid."""


class InvalidEndpointsError(CharmLoggingError):
    """Raised if an endpoint is invalid."""


@contextmanager
def charm_logging_disabled():
    """Contextmanager to temporarily disable charm logging.

    For usage in tests.
    """
    previous = os.getenv(CHARM_LOGGING_ENABLED)
    os.environ[CHARM_LOGGING_ENABLED] = "0"

    yield

    if previous is None:
        os.environ.pop(CHARM_LOGGING_ENABLED)
    else:
        os.environ[CHARM_LOGGING_ENABLED] = previous


_C = TypeVar("_C", bound=Type[CharmBase])
_T = TypeVar("_T", bound=type)
_F = TypeVar("_F", bound=Type[Callable])


def _get_logging_endpoints(
    logging_endpoints_getter: _EndpointGetterType, self: CharmBase, charm: Type[CharmBase]
):
    logging_endpoints: Optional[Sequence[str]]

    if isinstance(logging_endpoints_getter, property):
        logging_endpoints = logging_endpoints_getter.__get__(self)
    else:  # method or callable
        logging_endpoints = logging_endpoints_getter(self)

    if logging_endpoints is None:
        logger.debug(
            f"Charm logging disabled. {charm.__name__}.{logging_endpoints_getter} returned None."
        )
        return None

    errors = []
    sanitized_logging_endponts = []
    if isinstance(logging_endpoints, str):
        errors.append("invalid return value: expected Iterable[str], got str")
    else:
        for endpoint in logging_endpoints:
            if isinstance(endpoint, str):
                sanitized_logging_endponts.append(endpoint)
            else:
                errors.append(f"invalid endpoint: expected string, got {endpoint!r}")

    if errors:
        raise InvalidEndpointsError(
            f"{charm}.{logging_endpoints_getter} should return an iterable of Loki push-api "
            "(-compatible) endpoints (strings); "
            f"ERRORS: {errors}"
        )

    return sanitized_logging_endponts


def _get_server_cert(
    server_cert_getter: _CertGetterType, self: CharmBase, charm: Type[CharmBase]
) -> Optional[str]:
    if isinstance(server_cert_getter, property):
        server_cert = server_cert_getter.__get__(self)
    else:  # method or callable
        server_cert = server_cert_getter(self)

    # we're assuming that the ca cert that signed this unit is the same that has signed loki's
    if server_cert is None:
        logger.debug(f"{charm.__name__}.{server_cert_getter} returned None: can't use https.")
        return None

    if not isinstance(server_cert, str) and not isinstance(server_cert, Path):
        raise ValueError(
            f"{charm}.{server_cert_getter} should return a valid path to a tls cert file (string | Path)); "
            f"got a {type(server_cert)!r} instead."
        )

    sc_path = Path(server_cert).absolute()
    if not sc_path.exists():
        raise RuntimeError(
            f"{charm}.{server_cert_getter} returned bad path {server_cert!r}: " f"file not found."
        )

    return str(sc_path)


def _setup_root_logger_initializer(
    charm: Type[CharmBase],
    logging_endpoints_getter: _EndpointGetterType,
    server_cert_getter: Optional[_CertGetterType],
    service_name: Optional[str] = None,
):
    """Patch the charm's initializer and inject a call to set up root logging."""
    original_init = charm.__init__

    @functools.wraps(original_init)
    def wrap_init(self: CharmBase, framework: Framework, *args, **kwargs):
        original_init(self, framework, *args, **kwargs)

        if not is_enabled():
            logger.debug("Charm logging DISABLED by env: skipping root logger initialization")
            return

        logging_endpoints = _get_logging_endpoints(logging_endpoints_getter, self, charm)

        if not logging_endpoints:
            return

        juju_topology = JujuTopology.from_charm(self)
        labels = {
            **juju_topology.as_dict(),
            "service_name": service_name or self.app.name,
            "juju_hook_name": os.getenv("JUJU_HOOK_NAME", ""),
        }
        server_cert: Optional[Union[str, Path]] = (
            _get_server_cert(server_cert_getter, self, charm) if server_cert_getter else None
        )

        root_logger = logging.getLogger()

        for url in logging_endpoints:
            handler = LokiHandler(
                url=url,
                labels=labels,
                cert=str(server_cert) if server_cert else None,
            )
            root_logger.addHandler(handler)

        logger.debug("Initialized LokiHandler and set up root logging for charm code.")
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
    >>> from charms.loki_k8s.v1.loki_push_api import LokiPushApiConsumer
    >>> from ops import CharmBase
    >>>
    >>> @log_charm(
    >>>         logging_endpoints="loki_push_api_urls",
    >>> )
    >>> class MyCharm(CharmBase):
    >>>
    >>>     def __init__(self, framework: Framework):
    >>>         ...
    >>>         self.logging = LokiPushApiConsumer(self, ...)
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
    logging_endpoints_getter: _EndpointGetterType,
    server_cert_getter: Optional[_CertGetterType] = None,
    service_name: Optional[str] = None,
) -> Type[CharmBase]:
    """Set up logging on this charm class.

    Use this function to setup automatic log forwarding for all logs emitted throughout executions of
    this charm.

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
