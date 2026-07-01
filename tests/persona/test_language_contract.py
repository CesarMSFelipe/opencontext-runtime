"""Persona language contract tests: no regional voice in generated artifacts.

Per openspec/changes/agentic-parity-engram-gentle/specs/general-agent-surface/spec.md
§R4 / REQ-GAS-004 — generated artifacts must not contain Rioplatense
voice markers (voseo, slang, exclamations) in proposal, design, tasks,
or code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Root of the SDD change artifacts
CHANGE_ROOT = (
    Path(__file__).parents[1] / "openspec" / "changes" / "agentic-parity-engram-gentle"
)

# Artifact files to check
ARTIFACT_GLOBS = [
    "proposal.md",
    "design.md",
    "design/*.md",
    "tasks.md",
    "tasks/*.md",
    "spec.md",
    "specs/*/spec.md",
]

# Rioplatense / regional voice markers that must NOT appear
# in generated technical artifacts
REGIONAL_MARKERS = re.compile(
    r"\b(vos|viste|che|dale|listo|genial|bárbaro|excelente|perfecto)\b",
    re.IGNORECASE,
)

SPANISH_EXCLAMATION = re.compile(r"[¡¿]")


class TestLanguageContract:
    def _artifact_files(self) -> list[Path]:
        """Yield every artifact file that matches the globs."""
        files: list[Path] = []
        for pattern in ARTIFACT_GLOBS:
            matched = list(CHANGE_ROOT.glob(pattern))
            files.extend(matched)
        return files

    def test_no_voseo_in_proposal(self) -> None:
        """Proposal uses neutral language."""
        proposal = CHANGE_ROOT / "proposal.md"
        if not proposal.is_file():
            pytest.skip("proposal.md not found")
        text = proposal.read_text(encoding="utf-8")
        matches = REGIONAL_MARKERS.findall(text)
        assert not matches, f"Regional markers found in proposal.md: {matches}"

    def test_no_voseo_in_design(self) -> None:
        """Design uses neutral language."""
        design = CHANGE_ROOT / "design.md"
        if not design.is_file():
            pytest.skip("design.md not found")
        text = design.read_text(encoding="utf-8")
        matches = REGIONAL_MARKERS.findall(text)
        assert not matches, f"Regional markers found in design.md: {matches}"

    def test_no_voseo_in_tasks(self) -> None:
        """Tasks uses neutral language."""
        tasks = CHANGE_ROOT / "tasks.md"
        if not tasks.is_file():
            pytest.skip("tasks.md not found")
        text = tasks.read_text(encoding="utf-8")
        matches = REGIONAL_MARKERS.findall(text)
        assert not matches, f"Regional markers found in tasks.md: {matches}"

    def test_no_exclamations_in_proposal(self) -> None:
        """Proposal has no Spanish exclamation marks."""
        proposal = CHANGE_ROOT / "proposal.md"
        if not proposal.is_file():
            pytest.skip("proposal.md not found")
        text = proposal.read_text(encoding="utf-8")
        matches = SPANISH_EXCLAMATION.findall(text)
        assert not matches, f"Spanish exclamation marks found in proposal: {matches}"

    def test_all_artifacts_use_neutral_language(self) -> None:
        """Every artifact file is free of regional markers."""
        for path in self._artifact_files():
            text = path.read_text(encoding="utf-8")
            regional = REGIONAL_MARKERS.findall(text)
            exclam = SPANISH_EXCLAMATION.findall(text)
            msg_parts = []
            if regional:
                msg_parts.append(f"regional markers: {regional}")
            if exclam:
                msg_parts.append(f"Spanish exclamation marks: {exclam}")
            assert not msg_parts, f"{path}: {'; '.join(msg_parts)}"

    def test_skill_md_has_no_voseo(self) -> None:
        """Portable SKILL.md files have no regional voice."""
        skills_dir = CHANGE_ROOT.parents[1] / "packages" / "opencontext_sdd" / "opencontext_sdd" / "skills"
        if not skills_dir.is_dir():
            pytest.skip("SDD skills directory not found")
        for skill_md in skills_dir.rglob("SKILL.md"):
            text = skill_md.read_text(encoding="utf-8")
            matches = REGIONAL_MARKERS.findall(text)
            assert not matches, f"Regional markers in {skill_md}: {matches}"
