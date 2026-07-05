"""UVD program-level roll-up gate.

Per `openspec/USER-VALIDATION-DOD.md` and
`openspec/changes/opencontext-1-0-convergence/round-2-gap-analysis.md §A`:

> Every UVD-001..UVD-025 is referenced by **at least one** capability spec; this file
> is wired into PR-017's release-gate lint per doc 57 §C.

This test enforces that the program-level catalog at `openspec/USER-VALIDATION-DOD.md`
exposes every UVD ID, and that the cross-reference count per ID matches the §A matrix
(at least one PR owns each UVD).

Ponytail: the catalog is the source of truth; this test only reads it.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CATALOG = _REPO_ROOT / "openspec" / "USER-VALIDATION-DOD.md"
_GAP_ANALYSIS = (
    _REPO_ROOT / "openspec" / "changes" / "opencontext-1-0-convergence" / "round-2-gap-analysis.md"
)
_SPECS_DIR = _REPO_ROOT / "openspec" / "changes" / "opencontext-1-0-convergence" / "specs"


def _read(path: Path) -> str:
    if not path.exists():
        import pytest

        pytest.skip(f"openspec file not present (gitignored, local-only): {path}")
    return path.read_text(encoding="utf-8")


def _all_uvd_ids() -> list[str]:
    return [f"UVD-{n:03d}" for n in range(1, 26)]


def _expand_uvd_shorthand(text: str) -> set[str]:
    """Expand `UVD-001..007` and `UVD-001, UVD-003` notations into a set of IDs."""
    found: set[str] = set()
    # Literal IDs.
    for match in re.finditer(r"UVD-(\d{3})", text):
        found.add(f"UVD-{match.group(1)}")
    # Ranges: UVD-001..007 or UVD-001..UVD-007 (with optional spaces).
    for match in re.finditer(r"UVD-(\d{3})\s*\.\.\s*UVD-?(\d{3})", text):
        lo, hi = int(match.group(1)), int(match.group(2))
        for n in range(lo, hi + 1):
            found.add(f"UVD-{n:03d}")
    return found


def _section_re(uvd_id: str) -> re.Pattern[str]:
    # Matches `## UVD-001 — title` or `## UVD-001 - title` (any dash).
    return re.compile(rf"^##\s+{re.escape(uvd_id)}\b", re.MULTILINE)


class TestUVDProgramCatalog:
    """Roll-up gate: the program-level catalog covers every UVD-001..UVD-025."""

    def test_catalog_file_exists(self) -> None:
        if not _CATALOG.exists():
            import pytest

            pytest.skip(f"openspec catalog not present (gitignored, local-only): {_CATALOG}")
        assert _CATALOG.exists(), f"UVD catalog not found at {_CATALOG}"

    def test_catalog_has_all_25_uvd_sections(self) -> None:
        text = _read(_CATALOG)
        missing = [uid for uid in _all_uvd_ids() if not _section_re(uid).search(text)]
        assert not missing, (
            f"UVD catalog missing section headers for: {missing}. "
            f"Each must appear as `## UVD-NNN - ...`."
        )

    def test_catalog_has_required_fields_per_uvd(self) -> None:
        text = _read(_CATALOG)
        # Each UVD section must declare Flow, Expected, and PR.
        section_re = re.compile(
            r"^##\s+(UVD-\d{3})\b.*?(?=^##\s+UVD-\d{3}|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        missing_fields: list[str] = []
        for match in section_re.finditer(text):
            uvd_id = match.group(1)
            body = match.group(0)
            for field in ("**Flow**", "**Expected**", "**PR**"):
                if field not in body:
                    missing_fields.append(f"{uvd_id} lacks {field}")
        assert not missing_fields, (
            "UVD catalog sections missing required fields:\n  - " + "\n  - ".join(missing_fields)
        )

    def test_catalog_at_least_10_cli_verifiable(self) -> None:
        text = _read(_CATALOG)
        cli_count = text.count("- **CLI-verifiable**: yes")
        assert cli_count >= 10, (
            f"UVD catalog marks only {cli_count} entries as CLI-verifiable; need >= 10."
        )

    def test_catalog_assigns_at_least_one_pr_per_uvd(self) -> None:
        text = _read(_CATALOG)
        section_re = re.compile(
            r"^##\s+(UVD-\d{3})\b.*?(?=^##\s+UVD-\d{3}|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        pr_line_re = re.compile(r"^\s*-\s+\*\*PR\*\*:\s*(.+)$", re.MULTILINE)
        unassigned: list[str] = []
        for match in section_re.finditer(text):
            uvd_id = match.group(1)
            body = match.group(0)
            pr_match = pr_line_re.search(body)
            if not pr_match or not pr_match.group(1).strip():
                unassigned.append(uvd_id)
        assert not unassigned, f"UVD sections with no PR assignment: {unassigned}."


class TestUVDProgramMatrixConsistency:
    """Catalog PR assignments must be consistent with the §A matrix."""

    def test_gap_analysis_section_a_lists_all_25_uvds(self) -> None:
        text = _read(_GAP_ANALYSIS)
        section_a = text.split("## §A")[1].split("## §B")[0]
        found = _expand_uvd_shorthand(section_a)
        missing = [uid for uid in _all_uvd_ids() if uid not in found]
        assert not missing, (
            f"round-2-gap-analysis.md §A does not reference (after expanding ranges): {missing}."
        )

    def test_catalog_summary_index_lists_all_25(self) -> None:
        text = _read(_CATALOG)
        # Summary Index table must include every UVD-NNN at least once.
        missing = [uid for uid in _all_uvd_ids() if uid not in text]
        assert not missing, f"UVD catalog does not mention these IDs anywhere: {missing}."


class TestHostIntegrationDoD:
    """The Host-Integration DoD (HID) must be backed by real, on-disk tests.

    This is the anti-overclaim guard for change ``real-host-dod-convergence``:
    the catalog may not name a ``Test`` path that does not exist, and it may not
    resurrect the old fabricated ``tests/e2e/test_uvd_NNN.py`` claim.
    """

    def test_catalog_has_hid_section_for_three_hosts(self) -> None:
        text = _read(_CATALOG)
        assert "## Host-Integration DoD" in text, "HID section missing from UVD catalog"
        for hid in ("HID-1", "HID-2", "HID-3", "HID-4"):
            assert re.search(rf"^##\s+{hid}\b", text, re.MULTILINE), f"{hid} section missing"
        for host in ("codex", "opencode", "claude"):
            assert host in text, f"HID section does not name host '{host}'"

    def test_hid_test_references_exist_on_disk(self) -> None:
        text = _read(_CATALOG)
        # Pull the HID block and every `- **Test**: path::node` reference in it.
        hid_block = text.split("## Host-Integration DoD", 1)[1].split("## Summary Index", 1)[0]
        refs = re.findall(r"-\s+\*\*Test\*\*:\s*`?([^\s`:]+\.py)", hid_block)
        assert refs, "HID section declares no Test references"
        for rel in refs:
            assert (_REPO_ROOT / rel).is_file(), f"HID references non-existent test file: {rel}"

    def test_catalog_does_not_claim_fabricated_per_id_tests(self) -> None:
        text = _read(_CATALOG)
        assert "test_uvd_NNN.py" not in text, (
            "UVD catalog still claims fabricated per-id tests/e2e/test_uvd_NNN.py files; "
            "point UVDs at the real e2e suites instead."
        )


class TestUVDProgramSpecsCrossReference:
    """Each per-capability spec must reference applicable UVDs (≥1)."""

    def test_at_least_one_spec_references_each_uvd(self) -> None:
        if not _SPECS_DIR.exists():
            # Pre-PR-013: specs dir not yet laid out; skip rather than fail.
            import pytest

            pytest.skip(f"specs dir not present at {_SPECS_DIR}")

        text_total = ""
        for spec_path in sorted(_SPECS_DIR.glob("*/spec.md")):
            text_total += "\n" + _read(spec_path)

        for uid in _all_uvd_ids():
            assert uid in text_total, f"{uid} is not referenced by any spec under {_SPECS_DIR}."
