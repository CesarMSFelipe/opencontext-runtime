"""install() writes a loadable config AND copies the SDD skill set.

RED first: today ``InstallationManager.install()`` reports ``status='installed'``
but never writes ``opencontext.yaml``; ``_install_skills`` returns a hardcoded
``{"status": "installed"}`` and copies no files.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import SecurityMode, load_config
from opencontext_core.install_manager import InstallationManager, InstallProfile

# The SDD agentic skill set the developer drives, plus the agent SKILL.md template.
REQUIRED_SDD_SKILLS = ("sdd-new", "sdd-apply", "sdd-verify", "sdd-archive")


def test_install_writes_loadable_config(tmp_path: Path) -> None:
    """install() must write an opencontext.yaml that load_config can parse."""
    manager = InstallationManager()
    result = manager.install(
        profile=InstallProfile.FULL,
        targets=[],
        components=["skills"],
        backup=False,
        yes=True,
        root=tmp_path,
    )

    assert result["status"] == "installed"

    config_path = tmp_path / "opencontext.yaml"
    assert config_path.exists(), "install() did not write opencontext.yaml"
    assert config_path.stat().st_size > 0

    # The written config must round-trip through the real validator.
    config = load_config(config_path)
    assert config.security.mode in set(SecurityMode)


def test_install_copies_sdd_skill_set(tmp_path: Path) -> None:
    """_install_skills must copy the full SDD agentic skill set to disk."""
    manager = InstallationManager()
    manager.install(
        profile=InstallProfile.FULL,
        targets=[],
        components=["skills"],
        backup=False,
        yes=True,
        root=tmp_path,
    )

    skills_dir = tmp_path / ".opencontext" / "skills"
    assert skills_dir.exists(), "skills directory was not created"

    for skill in REQUIRED_SDD_SKILLS:
        skill_md = skills_dir / skill / "SKILL.md"
        assert skill_md.exists(), f"missing SDD skill file: {skill_md}"
        assert skill_md.read_text(encoding="utf-8").strip(), f"empty skill file: {skill_md}"

    # The opencontext-agent SKILL.md template must also land on disk.
    agent_skill = skills_dir / "opencontext-agent" / "SKILL.md"
    assert agent_skill.exists(), "missing opencontext-agent/SKILL.md"
    assert agent_skill.read_text(encoding="utf-8").strip()


def test_install_skills_reports_files_written(tmp_path: Path) -> None:
    """_install_skills must report the files it actually wrote, not a hardcoded note."""
    manager = InstallationManager()
    result = manager.install(
        profile=InstallProfile.FULL,
        targets=[],
        components=["skills"],
        backup=False,
        yes=True,
        root=tmp_path,
    )

    skills_results = [r for r in result["results"] if r.get("component") == "skills"]
    assert skills_results, "no skills result reported"
    skills_result = skills_results[0]
    assert skills_result["status"] == "installed"
    # Must enumerate the real files written (assert-backed existence).
    written = skills_result.get("files", [])
    assert written, "skills result did not list any written files"
    for path_str in written:
        assert Path(path_str).exists(), f"reported skill file does not exist: {path_str}"
