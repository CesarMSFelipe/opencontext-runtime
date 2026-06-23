"""``_install_skills`` re-sync prunes the migrated-away ``sdd-*`` skill dirs.

Workstream D1 of ``oc-memory-parity-and-polish``: the source templates already
ship the correct ``oc-*`` set, but a project installed before the rename keeps
stale ``sdd-apply`` / ``sdd-archive`` / ``sdd-new`` / ``sdd-verify`` dirs on disk
forever, because ``_install_skills`` only ever *adds* the ``oc-*`` set and never
removed the old names. The re-sync MUST remove ONLY the known-stale ``sdd-*`` set
and MUST NOT touch unrelated user-customized skills (R7 / TR3 — no blanket wipe).

Home isolation is provided by this package's autouse ``isolate_user_home``
fixture; ``root=tmp_path`` keeps the on-disk skills under tmp.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.install_manager import InstallationManager, InstallProfile

# The exact stale set the rename left behind (design D1 / spec D1-REQ-1).
STALE_SDD_SKILLS = ("sdd-apply", "sdd-archive", "sdd-new", "sdd-verify")


def _install_skills(root: Path) -> dict:
    return InstallationManager().install(
        profile=InstallProfile.FULL,
        targets=[],
        components=["skills"],
        backup=False,
        yes=True,
        root=root,
    )


def test_resync_prunes_stale_sdd_skill_dirs(tmp_path: Path) -> None:
    """Pre-existing stale ``sdd-*`` dirs are gone after a re-sync; ``oc-*`` present."""
    skills_dir = tmp_path / ".opencontext" / "skills"
    # Simulate a pre-migration install: plant the stale sdd-* dirs on disk.
    for stale in STALE_SDD_SKILLS:
        d = skills_dir / stale
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text("# stale pre-migration skill\n", encoding="utf-8")

    _install_skills(tmp_path)

    for stale in STALE_SDD_SKILLS:
        assert not (skills_dir / stale).exists(), (
            f"stale skill dir was not pruned by re-sync: {stale}"
        )

    # The correct oc-* set must be present after the sync.
    for oc in ("oc-new", "oc-apply", "oc-verify", "oc-archive"):
        assert (skills_dir / oc / "SKILL.md").exists(), f"missing oc-* skill: {oc}"


def test_resync_preserves_unrelated_user_skill(tmp_path: Path) -> None:
    """A user's own (non-stale) installed skill survives the re-sync (R7)."""
    skills_dir = tmp_path / ".opencontext" / "skills"
    custom = skills_dir / "my-custom-skill"
    custom.mkdir(parents=True, exist_ok=True)
    sentinel = custom / "SKILL.md"
    sentinel.write_text("# user's own skill — must not be clobbered\n", encoding="utf-8")

    # Also plant a stale dir so the prune path actually runs.
    stale = skills_dir / "sdd-apply"
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "SKILL.md").write_text("# stale\n", encoding="utf-8")

    _install_skills(tmp_path)

    assert sentinel.exists(), "re-sync clobbered an unrelated user-customized skill"
    assert "user's own skill" in sentinel.read_text(encoding="utf-8")
    assert not stale.exists(), "stale sdd-apply was not pruned"


def test_resync_reports_pruned_dirs(tmp_path: Path) -> None:
    """The skills result enumerates what it pruned (assert-backed observability)."""
    skills_dir = tmp_path / ".opencontext" / "skills"
    for stale in STALE_SDD_SKILLS:
        (skills_dir / stale).mkdir(parents=True, exist_ok=True)

    result = _install_skills(tmp_path)
    skills_results = [r for r in result["results"] if r.get("component") == "skills"]
    assert skills_results, "no skills result reported"
    pruned = skills_results[0].get("pruned", [])
    assert sorted(pruned) == sorted(STALE_SDD_SKILLS), (
        f"re-sync did not report the pruned stale set: {pruned}"
    )
