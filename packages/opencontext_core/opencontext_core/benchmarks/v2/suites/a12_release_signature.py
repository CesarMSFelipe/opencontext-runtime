"""A12 — release signature: signed release artifact in dist/.

Checks whether a signed release artifact (wheel + signature file) is present
under ``dist/`` and that the marketplace signing machinery exists.

Honest blocked result per HONESTY RULE 2: if no signed artifact is present,
returns success=False naming the blocker — never a silent pass.

Signing machinery (``marketplace/signing.py``) is checked for existence as
evidence that the infrastructure is in place; absence is a separate blocker.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A12"
_REPO_ROOT = Path(__file__).resolve().parents[6]

# Accepted signature-file suffixes (wheel + detached-sig or cosign bundle).
_SIG_SUFFIXES: tuple[str, ...] = (".sig", ".asc", ".sigstore", ".bundle")

# The marketplace signing machinery (HMAC + publisher keys).
_SIGNING_MODULE = (
    _REPO_ROOT
    / "packages"
    / "opencontext_core"
    / "opencontext_core"
    / "marketplace"
    / "signing.py"
)


def run() -> BenchmarkResult:
    """Check for a signed release artifact in dist/ and signing infra presence."""
    # Check 1: signing machinery must exist.
    if not _SIGNING_MODULE.is_file():
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail="marketplace/signing.py not found — signing infrastructure missing",
        )

    # Check 2: dist/ must contain a signed artifact.
    dist_dir = _REPO_ROOT / "dist"
    if not dist_dir.is_dir():
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=(
                "no signed release artifact in dist/ — release infra pending"
                " (dist/ directory not found)"
            ),
        )

    sig_files = [f for f in dist_dir.iterdir() if f.suffix in _SIG_SUFFIXES]
    if not sig_files:
        # Honest blocked result — no signed artifact yet.
        artifacts = sorted(f.name for f in dist_dir.iterdir() if f.is_file())
        return BenchmarkResult(
            name=SUITE_ID,
            success=False,
            methodology_version=current_methodology_version(),
            detail=(
                "no signed release artifact in dist/ — release infra pending"
                f" (present: {', '.join(artifacts) or 'none'})"
            ),
        )

    return BenchmarkResult(
        name=SUITE_ID,
        success=True,
        methodology_version=current_methodology_version(),
        detail="",
        metrics={"sig_files": [f.name for f in sig_files]},
    )
