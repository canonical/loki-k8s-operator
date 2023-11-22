#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
"""Config builder for Loki Charmed Operator."""

import os

# Paths in workload container
HTTP_LISTEN_PORT = 3100
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

    def __init__(
        self,
        *,
        instance_addr: str,
        alertmanager_url: str,
        external_url: str,
        ingestion_rate_mb: int,
        ingestion_burst_size_mb: int,
        http_tls: bool = False,
    ):
        """Init method."""
        self.instance_addr = instance_addr
        self.alertmanager_url = alertmanager_url
        self.external_url = external_url
        self.ingestion_rate_mb = ingestion_rate_mb
        self.ingestion_burst_size_mb = ingestion_burst_size_mb
        self.http_tls = http_tls

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
            "limits_config": self._limits_config,
            "query_range": self._query_range,
            "chunk_store_config": self._chunk_store_config,
        }

    @property
    def _common(self) -> dict:
        return {
            "path_prefix": LOKI_DIR,
            "replication_factor": 1,
            "ring": {"instance_addr": self.instance_addr, "kvstore": {"store": "inmemory"}},
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
        # Reference: https://grafana.com/docs/loki/latest/configure/#ruler
        return {
            "alertmanager_url": self.alertmanager_url,
            "external_url": self.external_url,
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
            "http_listen_port": HTTP_LISTEN_PORT,
        }

        if self.http_tls:
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

    @property
    def _limits_config(self) -> dict:
        # Ref: https://grafana.com/docs/loki/latest/configure/#limits_config
        return {
            # For convenience, we use an integer but Loki takes a float
            "ingestion_rate_mb": float(self.ingestion_rate_mb),
            "ingestion_burst_size_mb": float(self.ingestion_burst_size_mb),
            # The per-stream limits are intentionally set to match the per-user limits, to simplify UX and address the
            # case of one stream per user.
            "per_stream_rate_limit": f"{self.ingestion_rate_mb}MB",
            "per_stream_rate_limit_burst": f"{self.ingestion_burst_size_mb}MB",
            # This charmed operator is intended for running a single loki instances, so we don't need to split queries
            # https://community.grafana.com/t/too-many-outstanding-requests-on-loki-2-7-1/78249/9
            "split_queries_by_interval": "0",
        }

    @property
    def _query_range(self) -> dict:
        # Ref: https://grafana.com/docs/loki/latest/configure/#query_range
        return {
            "results_cache": {
                "cache": {
                    "embedded_cache": {
                        # https://community.grafana.com/t/too-many-outstanding-requests-on-loki-2-7-1/78249/11
                        "enabled": "true"
                    }
                }
            }
        }

    @property
    def _chunk_store_config(self) -> dict:
        # Ref: https://grafana.com/docs/loki/latest/configure/#chunk_store_config
        return {
            "chunk_cache_config": {
                "embedded_cache": {
                    # https://community.grafana.com/t/too-many-outstanding-requests-on-loki-2-7-1/78249/11
                    "enabled": "true"
                }
            }
        }
