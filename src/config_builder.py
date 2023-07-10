#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
"""Config builder for Loki Charmed Operator."""

import os


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
            "path_prefix": self._charm.loki_dir,
            "replication_factor": 1,
            "ring": {"instance_addr": self._charm.hostname, "kvstore": {"store": "inmemory"}},
            "storage": {
                "filesystem": {
                    "chunks_directory": self._charm.chunks_dir,
                    "rules_directory": self._charm.rules_dir,
                }
            },
        }

    @property
    def _ingester(self) -> dict:
        return {
            "wal": {
                "dir": os.path.join(self._charm.chunks_dir, "wal"),
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
                "cert_file": self._charm.loki_cert_path,  # HTTP server cert path.
                "key_file": self._charm.loki_key_path,  # HTTP server key path.
                "client_auth_type": "",  # HTTP TLS Client Auth type.
                "client_ca_file": "",  # HTTP TLS Client CA path.
            }

        return _server

    @property
    def _storage_config(self) -> dict:
        return {
            "boltdb": {"directory": self._charm.boltdb_dir},
            "filesystem": {"directory": self._charm.chunks_dir},
        }
