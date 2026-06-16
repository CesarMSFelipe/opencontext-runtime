"""Tests for SubAgentDelegate — callable LOCAL path and demoted MOCK path.

SubAgentDelegate MUST be structurally callable from the live
harness path for the LOCAL delegation mode, returning a well-formed
SubAgentResult from a registered handler. The MOCK delegation mode MUST be
usable only for tests and MUST NOT be selected by the live harness run path.
"""

from __future__ import annotations

from opencontext_core.agents.delegation import (
    DelegationMode,
    SubAgentDelegate,
    SubAgentResult,
)


class TestSubAgentDelegateCallable:
    def test_delegate_method_exists(self) -> None:
        """The class must expose delegate/register_handler as bound methods.

        Regression guard: a misplaced module-level function previously
        terminated the class body, leaving delegate/register_handler trapped
        as dead nested functions (the class became uncallable).
        """
        delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)
        assert callable(getattr(delegate, "delegate", None))
        assert callable(getattr(delegate, "register_handler", None))

    def test_local_delegation_returns_real_handler_output(self) -> None:
        """LOCAL mode returns the handler's output, not a mock."""
        delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)
        delegate.register_handler(
            "design",
            lambda ctx: {
                "status": "success",
                "output": f"design-for-{ctx['task']}",
                "artifacts": ["design.md"],
            },
        )

        result = delegate.delegate("design", {"task": "auth"})

        assert isinstance(result, SubAgentResult)
        assert result.status == "success"
        # Output is the handler's output, NOT the mock template.
        assert result.output == "design-for-auth"
        assert "Mock design result" not in result.output
        assert result.artifacts == ["design.md"]

    def test_local_delegation_unknown_phase_is_clean_error(self) -> None:
        """Without a handler, LOCAL mode returns a clean error, never a mock."""
        delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)
        result = delegate.delegate("spec", {"task": "auth"})

        assert result.status == "error"
        assert result.error is not None
        assert "No handler registered" in result.error
        assert "Mock spec result" not in result.output

    def test_mock_mode_still_works_for_tests(self) -> None:
        """MOCK mode remains usable for tests (explicit opt-in)."""
        delegate = SubAgentDelegate(mode=DelegationMode.MOCK)
        result = delegate.delegate("spec", {"task": "auth"})
        assert result.status == "success"
        assert "Mock spec result" in result.output
