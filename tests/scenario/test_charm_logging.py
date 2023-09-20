import json
import logging
from unittest.mock import MagicMock, patch

from charms.loki_k8s.v0.charm_logging import forward_logs
from charms.loki_k8s.v0.loki_push_api import LokiPushApiConsumer
from ops import CharmBase, Framework
from scenario import Context, State, Relation

@forward_logs(
        logging_endpoints="loki_push_api_endpoints",
)
class LoggingCharm(CharmBase):
    META = {'name': 'charlemagne',
            "requires": {"logging": {"interface": "loki_push_api"}}}

    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.loki = LokiPushApiConsumer(self)
        framework.observe(self.on.update_status, self._on_update_status)

    def _on_update_status(self, _):
        logging.warning("foo")

    @property
    def loki_push_api_endpoints(self):
        return [ep['url'] for ep in self.loki.loki_endpoints]


def test_without_loki(caplog):
    ctx = Context(LoggingCharm, meta=LoggingCharm.META)
    ctx.run('update-status', State())

    assert "continuing with logging DISABLED" in caplog.text


def test_with_loki(caplog):
    ctx = Context(LoggingCharm, meta=LoggingCharm.META)
    emit = MagicMock()
    with patch("logging_loki.handlers.LokiHandler.emit", emit):
        ctx.run('update-status', State(
            relations=[Relation("logging",
                                remote_units_data={0: {"endpoint": json.dumps({"url": "http://loki.logs/api/v1/yumyum"})}})]
        ))
    assert "continuing with logging DISABLED" not in caplog.text

    calls = emit.call_args_list
    assert emit.call_count == 3
    ops_setup, charm_logging_setup, charm_handler_msg = calls
    assert "Hello world." in ops_setup.args[0].msg
    assert "Emitting Juju event %s." == charm_logging_setup.args[0].msg
    assert "foo" == charm_handler_msg.args[0].msg