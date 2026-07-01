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


def test_default_handler_serves_get() -> None:
    from urllib.request import urlopen

    server = StudioServer(StudioConfig())
    server.start()
    server.serve_forever()
    try:
        host, port = server.bound_address
        with urlopen(f"http://{host}:{port}/", timeout=5) as resp:
            assert resp.status == 200
            assert b"opencontext studio" in resp.read()
    finally:
        server.stop()
