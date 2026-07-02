"""Unit gate: KG warning must degrade is_healthy to False.

C4 (product-closure-r13): verification.py:48-49 sets is_healthy = failures == 0.
This means a Knowledge Graph warning (e.g., stale entries, not-yet-indexed) keeps
is_healthy=True even though the KG is degraded.

Fix: is_healthy = failures == 0 and not any KG warning present.
Non-KG warnings (Python version, no config yet) remain advisory and must NOT
degrade healthy status.
"""

from __future__ import annotations

from opencontext_core.verification import CheckResult, VerificationReport


def _make_report(*results: CheckResult) -> VerificationReport:
    return VerificationReport(results=list(results))


# -- Scenarios that MUST degrade healthy --

def test_kg_warning_yields_healthy_false() -> None:
    """A Knowledge Graph warning must make is_healthy=False.

    Strict TDD: fails until verification.py is fixed.
    """
    report = _make_report(
        CheckResult("Knowledge Graph", "warning", "No database yet"),
        CheckResult("Python Version", "passed", "Python 3.12"),
    )
    assert report.is_healthy is False, (
        "A 'Knowledge Graph' warning must degrade is_healthy to False"
    )


def test_kg_failure_yields_healthy_false() -> None:
    """A Knowledge Graph failure (hard error) must also make is_healthy=False."""
    report = _make_report(
        CheckResult("Knowledge Graph", "failed", "Database error: disk full"),
    )
    assert report.is_healthy is False


# -- Scenarios that must NOT degrade healthy --

def test_python_version_warning_does_not_degrade_healthy() -> None:
    """Advisory warnings (Python version, no config) must keep is_healthy=True."""
    report = _make_report(
        CheckResult("Python Version", "warning", "Python 3.11 < 3.12 recommended"),
        CheckResult("User Config", "passed", "Config at /some/path"),
    )
    assert report.is_healthy is True, (
        "Python version warning must not degrade is_healthy"
    )


def test_no_config_warning_does_not_degrade_healthy() -> None:
    """'No config yet' warning is advisory and must keep is_healthy=True."""
    report = _make_report(
        CheckResult("User Config", "warning", "No config yet"),
    )
    assert report.is_healthy is True


def test_all_passed_is_healthy() -> None:
    """All-passed report must be healthy."""
    report = _make_report(
        CheckResult("Knowledge Graph", "passed", "Database with 100 files"),
        CheckResult("Python Version", "passed", "Python 3.12"),
    )
    assert report.is_healthy is True


def test_kg_skipped_does_not_degrade_healthy() -> None:
    """Skipped KG check (feature disabled) must keep is_healthy=True."""
    report = _make_report(
        CheckResult("Knowledge Graph", "skipped", "Not enabled"),
        CheckResult("Python Version", "passed", "Python 3.12"),
    )
    assert report.is_healthy is True
