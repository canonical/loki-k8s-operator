#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
"""Config builder for Loki Charmed Operator."""

import os

# Paths in workload container
LOKI_CONFIG_DIR = "/etc/loki"
LOKI_CONFIG = os.path.join(LOKI_CONFIG_DIR, "loki-local-config.yaml")
LOKI_CERTS_DIR = os.path.join(LOKI_CONFIG_DIR, "certs")

CERT_FILE = os.path.join(LOKI_CERTS_DIR, "loki.cert.pem")
KEY_FILE = os.path.join(LOKI_CERTS_DIR, "loki.key.pem")

LOKI_DIR = "/loki"
CHUNKS_DIR = os.path.join(LOKI_DIR, "chunks")
BOLTDB_DIR = os.path.join(LOKI_DIR, "boltdb-shipper-active")
RULES_DIR = os.path.join(LOKI_DIR, "rules")


class ConfigBuilder:
    """Loki configuration builder class.

    Some minimal configuration is required for Loki to start, including: storage paths, schema,
    ring.

    Reference: https://grafana.com/docs/loki/latest/configuration/
    """

    _target: str = "all"
    _auth_enabled: bool = False

    def __init__(self, charm):
        """Init method."""
        self._charm = charm

    def build(self) -> dict:
        """Build Loki config dictionary."""
        return {
            "target": self._target,
            "auth_enabled": self._auth_enabled,
            "common": self._common,
            "ingester": self._ingester,
            "ruler": self._ruler,
            "schema_config": self._schema_config,
            "server": self._server,
            "storage_config": self._storage_config,
        }

    @property
    def _common(self) -> dict:
        return {
            "path_prefix": LOKI_DIR,
            "replication_factor": 1,
            "ring": {"instance_addr": self._charm.hostname, "kvstore": {"store": "inmemory"}},
            "storage": {
                "filesystem": {
                    "chunks_directory": CHUNKS_DIR,
                    "rules_directory": RULES_DIR,
                }
            },
        }

    @property
    def _ingester(self) -> dict:
        return {
            "wal": {
                "dir": os.path.join(CHUNKS_DIR, "wal"),
                "enabled": True,
                "flush_on_shutdown": True,
            }
        }

    @property
    def _ruler(self) -> dict:
        return {
            "alertmanager_url": self._charm._alerting_config(),
            "external_url": self._charm._external_url,
        }

    @property
    def _schema_config(self) -> dict:
        return {
            "configs": [
                {
                    "from": "2020-10-24",
                    "index": {"period": "24h", "prefix": "index_"},
                    "object_store": "filesystem",
                    "schema": "v11",
                    "store": "boltdb",
                }
            ]
        }

    @property
    def _server(self) -> dict:
        _server = {
            "http_listen_address": "0.0.0.0",
            "http_listen_port": self._charm._port,
        }

        if self._charm.server_cert.cert:
            _server["http_tls_config"] = {
                "cert_file": CERT_FILE,  # HTTP server cert path.
                "key_file": KEY_FILE,  # HTTP server key path.
            }

        return _server

    @property
    def _storage_config(self) -> dict:
        return {
            "boltdb": {"directory": BOLTDB_DIR},
            "filesystem": {"directory": CHUNKS_DIR},
        }
