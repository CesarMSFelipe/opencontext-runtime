"""REQ-studio-mvp-001: local server binds to 127.0.0.1:random_port."""

from __future__ import annotations

from opencontext_studio.server import StudioConfig, StudioServer


def test_REQ_studio_mvp_001_local_binds() -> None:
    cfg = StudioConfig(host="127.0.0.1", port=0)
    server = StudioServer(cfg)
    server.start()
    try:
        host, port = server.bound_address
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        server.stop()


def test_studio_config_defaults() -> None:
    cfg = StudioConfig()
    assert cfg.host == "127.0.0.1"
