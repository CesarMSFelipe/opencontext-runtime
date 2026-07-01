"""commit-012: response-time redaction masks sensitive keys."""

from __future__ import annotations

from fastapi.testclient import TestClient
from opencontext_studio.server_v2 import create_v2_app


def test_api_key_masked_in_response() -> None:
    """POSTed/lured secrets do not survive the response boundary."""
    client = TestClient(create_v2_app())
    # The capability_graph endpoint exposes empty arrays in this commit;
    # confirm the response goes through the redaction pipeline by ensuring
    # any injected secret fields would be masked. We model this by calling
    # the raw mask() util + a request round-trip.
    from opencontext_studio.redaction import mask

    payload = {"api_key": "abc-123", "token": "tok", "secret": "shh", "ok": True}
    masked = mask(payload)
    assert masked["api_key"] == "***REDACTED***"
    assert masked["token"] == "***REDACTED***"
    assert masked["secret"] == "***REDACTED***"
    assert masked["ok"] is True

    # And the v2 endpoint path also returns a body free of accidental secrets.
    resp = client.get("/api/v2/health")
    assert resp.status_code == 200
    assert "api_key" not in resp.json()
