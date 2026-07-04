"""Tests: P0.4 — sdd_cmd and sdd_routes stubs wired to real runner.

RED tests written first (Strict TDD). These verify:
1. _run_phase() calls opencontext_sdd.runner.run_phase (not a print stub).
2. _handle_ff() calls run_phase for each ff phase (not a placeholder print).
3. _handle_onboard() no longer prints the placeholder string.
4. FastAPI POST /v1/sdd/{phase} calls run_phase (no 'PR4 wires real runner' in response).
5. FastAPI POST /v1/sdd/continue calls dispatcher, no placeholder in prompt.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    from opencontext_cli.commands.sdd_cmd import add_sdd_parser

    parent = argparse.ArgumentParser(prog="opencontext")
    sub = parent.add_subparsers(dest="command", required=True)
    add_sdd_parser(sub)
    return parent


# ---------------------------------------------------------------------------
# CLI: _run_phase wired to runner.run_phase
# ---------------------------------------------------------------------------


class TestRunPhaseWiring:
    """_run_phase must call opencontext_sdd.runner.run_phase, not just print."""

    def test_run_phase_calls_runner(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """_run_phase delegates to runner.run_phase and prints envelope JSON."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        from opencontext_cli.commands.sdd_cmd import _run_phase

        fake_envelope = PhaseResultEnvelope(
            status="ok",
            executive_summary="Phase 'apply' dispatched.",
            artifacts={},
            next_recommended="verify",
            risks=[],
            skill_resolution="paths-injected",
            phase="apply",
            trace_id="",
        )

        with patch(
            "opencontext_cli.commands.sdd_cmd.run_phase", return_value=fake_envelope
        ) as mock_run:
            _run_phase("apply", tmp_path, "my-change")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs is not None
        # Must pass phase as first positional
        assert (
            call_kwargs.args[0] == "apply"
            or call_kwargs.kwargs.get("phase") == "apply"
            or (len(call_kwargs.args) > 0 and call_kwargs.args[0] == "apply")
        )

    def test_run_phase_output_is_json(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """_run_phase must emit JSON (envelope), not the old debug string."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        from opencontext_cli.commands.sdd_cmd import _run_phase

        fake_envelope = PhaseResultEnvelope(
            status="ok",
            executive_summary="Ready for phase 'verify'.",
            artifacts={},
            next_recommended="verify",
            risks=[],
            skill_resolution="paths-injected",
            phase="apply",
            trace_id="",
        )

        with patch("opencontext_cli.commands.sdd_cmd.run_phase", return_value=fake_envelope):
            _run_phase("apply", tmp_path, "my-change")

        captured = capsys.readouterr()
        import json

        # Output must be valid JSON
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert data["next_recommended"] == "verify"

    def test_run_phase_does_not_print_running_phase_string(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """Old debug string 'Running phase' must NOT appear in output."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        from opencontext_cli.commands.sdd_cmd import _run_phase

        fake_envelope = PhaseResultEnvelope(
            status="ok",
            executive_summary="ok",
            artifacts={},
            next_recommended="verify",
            risks=[],
            skill_resolution="paths-injected",
            phase="spec",
            trace_id="",
        )

        with patch("opencontext_cli.commands.sdd_cmd.run_phase", return_value=fake_envelope):
            _run_phase("spec", tmp_path, "test-change")

        captured = capsys.readouterr()
        assert "Running phase" not in captured.out


# ---------------------------------------------------------------------------
# CLI: _handle_ff wired (no placeholder)
# ---------------------------------------------------------------------------


class TestHandleFf:
    """_handle_ff must not print the 'ships in PR4 — placeholder' string."""

    def test_handle_ff_no_placeholder(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """_handle_ff must not emit the placeholder message."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        from opencontext_cli.commands.sdd_cmd import _handle_ff

        fake = PhaseResultEnvelope(
            status="ok",
            executive_summary="ok",
            artifacts={},
            next_recommended="apply",
            risks=[],
            skill_resolution="paths-injected",
            phase="tasks",
            trace_id="",
        )

        with patch("opencontext_cli.commands.sdd_cmd.run_phase", return_value=fake):
            _handle_ff("my-change", tmp_path, False)

        captured = capsys.readouterr()
        assert "ships in PR4" not in captured.out
        assert "placeholder" not in captured.out

    def test_handle_ff_calls_run_phase_for_ff_phases(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """_handle_ff calls run_phase for each of the 4 fast-forward phases."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        from opencontext_cli.commands.sdd_cmd import _handle_ff

        fake = PhaseResultEnvelope(
            status="ok",
            executive_summary="ok",
            artifacts={},
            next_recommended="tasks",
            risks=[],
            skill_resolution="paths-injected",
            phase="propose",
            trace_id="",
        )

        with patch("opencontext_cli.commands.sdd_cmd.run_phase", return_value=fake) as mock_run:
            _handle_ff("my-change", tmp_path, False)

        # ff = propose + spec + design + tasks (4 phases)
        assert mock_run.call_count == 4
        called_phases = [c.args[0] for c in mock_run.call_args_list]
        assert called_phases == ["propose", "spec", "design", "tasks"]


# ---------------------------------------------------------------------------
# CLI: _handle_onboard — no placeholder
# ---------------------------------------------------------------------------


class TestHandleOnboard:
    def test_handle_onboard_no_placeholder(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """_handle_onboard must not emit the 'ships in PR4' placeholder."""
        from opencontext_cli.commands.sdd_cmd import _handle_onboard

        _handle_onboard(tmp_path, False)

        captured = capsys.readouterr()
        assert "ships in PR4" not in captured.out
        assert "placeholder" not in captured.out


# ---------------------------------------------------------------------------
# FastAPI: POST /v1/sdd/{phase} wired to run_phase
# ---------------------------------------------------------------------------


class TestSddPhaseRouteWired:
    """POST /v1/sdd/{phase} must call run_phase, not return the PR4 note."""

    def _client(self) -> TestClient:
        from opencontext_api.main import app

        return TestClient(app)

    def test_phase_route_no_pr4_note(self) -> None:
        """POST /v1/sdd/apply must not return 'PR4 wires real runner' in body."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        fake = PhaseResultEnvelope(
            status="ok",
            executive_summary="apply dispatched",
            artifacts={},
            next_recommended="verify",
            risks=[],
            skill_resolution="paths-injected",
            phase="apply",
            trace_id="",
        )

        with patch("opencontext_api.sdd_routes.run_phase", return_value=fake):
            resp = self._client().post("/v1/sdd/apply", json={"change": "test", "cwd": "."})

        assert resp.status_code == 200
        body = resp.json()
        # The PR4 placeholder note must be gone
        assert body.get("note") != "PR4 wires real runner"
        assert "PR4" not in str(body)

    def test_phase_route_returns_envelope_fields(self) -> None:
        """POST /v1/sdd/spec must return envelope fields (status, next_recommended)."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        fake = PhaseResultEnvelope(
            status="ok",
            executive_summary="spec dispatched",
            artifacts={},
            next_recommended="design",
            risks=[],
            skill_resolution="paths-injected",
            phase="spec",
            trace_id="",
        )

        with patch("opencontext_api.sdd_routes.run_phase", return_value=fake):
            resp = self._client().post("/v1/sdd/spec", json={"change": "test", "cwd": "."})

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ok"
        assert body.get("next_recommended") == "design"

    def test_phase_route_calls_run_phase_with_right_args(self) -> None:
        """POST /v1/sdd/design must call run_phase(phase='design', change=..., cwd=...)."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        fake = PhaseResultEnvelope(
            status="ok",
            executive_summary="design dispatched",
            artifacts={},
            next_recommended="tasks",
            risks=[],
            skill_resolution="paths-injected",
            phase="design",
            trace_id="",
        )

        with patch("opencontext_api.sdd_routes.run_phase", return_value=fake) as mock_run:
            self._client().post("/v1/sdd/design", json={"change": "my-change", "cwd": "/tmp"})

        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("change") == "my-change"


# ---------------------------------------------------------------------------
# FastAPI: POST /v1/sdd/continue — no PR4 placeholder
# ---------------------------------------------------------------------------


class TestSddContinueRouteWired:
    def _client(self) -> TestClient:
        from opencontext_api.main import app

        return TestClient(app)

    def test_continue_route_no_pr4_placeholder(self) -> None:
        """POST /v1/sdd/continue must not return '(PR4 wires real runner)' in prompt."""
        resp = self._client().post("/v1/sdd/continue", json={"change": "test", "cwd": "."})
        assert resp.status_code == 200
        body = resp.json()
        prompt = body.get("prompt", "")
        assert "PR4 wires real runner" not in prompt
