"""Tests for Runtime Core models and enums (SPEC RC-002/004/009/011/012)."""

from __future__ import annotations

from opencontext_core.errors import OpenContextError
from opencontext_core.runtime.errors import RuntimeErrorCode, RuntimeFailure
from opencontext_core.runtime.events import EventCategory, RuntimeEvent
from opencontext_core.runtime.modes import RuntimeMode
from opencontext_core.runtime.run import NodeResult, RuntimeRun
from opencontext_core.runtime.session import RuntimeSession, SessionStatus


class TestSessionStatus:
    def test_has_exactly_nine_members(self) -> None:
        assert len(list(SessionStatus)) == 9

    def test_includes_book_eight_plus_cancelled(self) -> None:
        expected = {
            "created",
            "running",
            "waiting_for_approval",
            "paused",
            "completed",
            "failed",
            "escalated",
            "archived",
            "cancelled",
        }
        assert {s.value for s in SessionStatus} == expected


class TestRuntimeMode:
    def test_has_exactly_six_modes(self) -> None:
        assert len(list(RuntimeMode)) == 6

    def test_members(self) -> None:
        assert {m.value for m in RuntimeMode} == {
            "run_to_completion",
            "interactive",
            "step",
            "dry_run",
            "simulate",
            "resume",
        }


class TestEventCategory:
    def test_has_exactly_sixteen_categories(self) -> None:
        assert len(list(EventCategory)) == 16

    def test_required_categories_present(self) -> None:
        required = {
            "session",
            "workflow",
            "node",
            "harness",
            "policy",
            "context",
            "memory",
            "kg",
            "skill",
            "persona",
            "provider",
            "mutation",
            "inspection",
            "diagnosis",
            "escalation",
            "consolidation",
        }
        assert {c.value for c in EventCategory} == required


class TestRuntimeErrorCode:
    def test_has_exactly_nine_codes(self) -> None:
        assert len(list(RuntimeErrorCode)) == 9

    def test_codes(self) -> None:
        assert {c.value for c in RuntimeErrorCode} == {
            "workflow_not_found",
            "invalid_transition",
            "policy_denied",
            "capability_missing",
            "output_contract_failed",
            "mutation_failed",
            "inspection_failed",
            "provider_failed",
            "resume_failed",
        }


class TestRuntimeFailure:
    def test_carries_code_recoverability_and_next_action(self) -> None:
        err = RuntimeFailure(
            RuntimeErrorCode.INVALID_TRANSITION,
            "spec cannot transition to apply",
            recoverable=True,
            next_action="satisfy the failing test gate",
            user_summary="Apply is blocked until tests fail first.",
        )
        assert err.code == RuntimeErrorCode.INVALID_TRANSITION
        assert err.recoverable is True
        assert err.next_action == "satisfy the failing test gate"
        assert err.user_summary == "Apply is blocked until tests fail first."

    def test_is_an_opencontext_error(self) -> None:
        # Existing ``except OpenContextError`` handlers keep catching it.
        err = RuntimeFailure(
            RuntimeErrorCode.CAPABILITY_MISSING, "no docker", recoverable=False
        )
        assert isinstance(err, OpenContextError)
        # User summary defaults to the message when not supplied.
        assert err.user_summary == "no docker"


class TestSchemaVersions:
    def test_session_schema_version(self) -> None:
        session = RuntimeSession(session_id="s", root="/", task="t", profile="balanced")
        assert session.schema_version == "opencontext.session.v1"
        assert session.status == SessionStatus.created
        assert session.active_run_id is None

    def test_run_schema_version(self) -> None:
        run = RuntimeRun(run_id="r", session_id="s", workflow_id="wf")
        assert run.schema_version == "opencontext.run.v1"

    def test_event_schema_version(self) -> None:
        event = RuntimeEvent(session_id="s", type="session.created", status="ok")
        assert event.schema_version == "opencontext.runtime_event.v1"
        assert event.category == "session"

    def test_node_result_schema_version(self) -> None:
        node = NodeResult(
            session_id="s", run_id="r", workflow_id="wf", node_id="n", status="completed"
        )
        assert node.schema_version == "opencontext.node_result.v1"
