""" Charm code instrumentation library, offering the option to redirect all juju-log output to a
loki instance over loki_push_api.


"""
import functools
import logging
import os
from contextlib import contextmanager
from typing import Union, Callable, Sequence, Type, Optional, TYPE_CHECKING

from ops import Framework, CharmBase

if TYPE_CHECKING:
    from ops.model import _ModelBackend  # noqa


# The unique Charmhub library identifier, never change it
LIBID = "52ee6051f4e54aedaa60aa04134d1a6d"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

logger = logging.getLogger("charm_logging")

_GetterType = Union[Callable[[CharmBase], Optional[str]], property]

CHARM_LOGGING_ENABLED = "CHARM_LOGGING_ENABLED"


def is_enabled() -> bool:
    """Whether charm logging is enabled."""
    return os.getenv(CHARM_LOGGING_ENABLED, "1") == "1"


@contextmanager
def charm_logging_disabled():
    """Contextmanager to temporarily disable charm logging.

    For usage in tests.
    """
    previous = os.getenv(CHARM_LOGGING_ENABLED, "1")
    os.environ[CHARM_LOGGING_ENABLED] = "0"
    yield
    os.environ[CHARM_LOGGING_ENABLED] = previous


def _get_logging_endpoints(logging_endpoints_getter, self, charm):
    if isinstance(logging_endpoints_getter, property):
        logging_endpoints = logging_endpoints_getter.__get__(self)
    else:  # method or callable
        logging_endpoints = logging_endpoints_getter(self)

    if not logging_endpoints:
        logger.warning(
            f"{charm}.{getattr(logging_endpoints_getter, '__qualname__', str(logging_endpoints_getter))} "
            f"returned falsy result; continuing with logging DISABLED."
        )
        return
    elif not all(isinstance(val, str) for val in logging_endpoints):
        raise TypeError(
            f"{charm}.{logging_endpoints_getter} should return a list of loki push api endpoints "
            f"(string); got {logging_endpoints} instead."
        )
    return logging_endpoints


def _get_server_cert(server_cert_getter, self, charm):
    if isinstance(server_cert_getter, property):
        server_cert = server_cert_getter.__get__(self)
    else:  # method or callable
        server_cert = server_cert_getter(self)

    if server_cert is None:
        logger.warning(
            f"{charm}.{server_cert_getter} returned None; continuing with INSECURE connection."
        )
        return
    elif not isinstance(server_cert, str):
        raise TypeError(
            f"{charm}.{server_cert_getter} should return a valid tls cert (string); "
            f"got {server_cert} instead."
        )
    logger.debug("Certificate successfully retrieved.")  # todo: some more validation?
    return server_cert


def _setup_log_forwarding(
        charm: Type[CharmBase],
        logging_endpoints_getter: _GetterType,
        server_cert_getter: Optional[_GetterType],

        # todo replace with extra labels
        service_name: Optional[str] = None,
):
    """Patch the framework's debug-log method."""
    original_init = charm.__init__

    @functools.wraps(original_init)
    def wrap_init(self: CharmBase, framework: Framework, *args, **kwargs):
        original_init(self, framework, *args, **kwargs)
        if not is_enabled():
            logger.info("Tracing DISABLED: skipping root span initialization")
            return

        labels = {
            "service.name": service_name,
            "charm_type": type(self).__name__,
            # juju topology
            "juju_unit": self.unit.name,
            "juju_application": self.app.name,
            "juju_model": self.model.name,
            "juju_model_uuid": self.model.uuid,
        }
        logging_endpoints = _get_logging_endpoints(logging_endpoints_getter, self, charm)
        if not logging_endpoints:
            return

        logger.debug(f"Setting up log push to endpoint: {logging_endpoints}")

        server_cert: Optional[str] = (
            _get_server_cert(server_cert_getter, self, charm) if server_cert_getter else None
        )
        insecure = False if server_cert else True

        # todo:
        # pushlogs
        original_juju_log = framework.model._backend.juju_log
        @functools.wraps(original_juju_log)
        def wrap_juju_log(self: "_ModelBackend", level, msg):
            raise Todo()

        framework.model._backend.juju_log = wrap_juju_log

    charm.__init__ = wrap_init


def forward_logs(
        logging_endpoints: Sequence[str],
        server_cert: Optional[str] = None,
        service_name: Optional[str] = None,
):
    """Autoinstrument the decorated charm with logging telemetry.

    Use this function to forward any logging output produced by the charm to a loki endpoint.
    The charm is expected to have a relation over loki_push_api.

    Usage:
    >>> from charms.loki_k8s.v0.charm_logging import forward_logs
    >>> from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer
    >>> from ops import CharmBase
    >>>
    >>> @forward_logs(
    >>>         logging_endpoints="loki_push_api_endpoints",
    >>> )
    >>> class MyCharm(CharmBase):
    >>>
    >>>     def __init__(self, framework: Framework):
    >>>         ...
    >>>         self.loki = LokiPushApiConsumer(self)
    >>>
    >>>     @property
    >>>     def loki_push_api_endpoints(self) -> Sequence[str]:
    >>>         return [ep['url'] for ep in self.loki.loki_endpoints]
    >>>
    :param server_cert: method or property on the charm type that returns an
        optional tls certificate to be used when sending logs to a remote server.
        If it returns None, an _insecure_ connection will be used.
    :param logging_endpoints: name of a property on the charm type that returns a list of loki
        push api endpoints. If empty, logging will be effectively disabled. Else, logs will be
        pushed to those endpoints.
    :param service_name: service name tag to attach to all logs generated by this charm.
        Defaults to the juju application name this charm is deployed under.
    """

    def _decorator(charm_type: Type[CharmBase]):
        """Autoinstrument the wrapped charmbase type."""
        logging_endpoints_getter = getattr(charm_type, logging_endpoints)
        server_cert_getter = getattr(charm_type, server_cert) if server_cert else None

        logger.info(f"instrumenting {charm_type}")
        _setup_log_forwarding(
            charm_type,
            logging_endpoints_getter,
            server_cert_getter=server_cert_getter,
            service_name=service_name,
        )

        return charm_type

    return _decorator
