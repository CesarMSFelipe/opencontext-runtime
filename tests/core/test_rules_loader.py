"""Tests for the unified rules loader (configurable rules engine)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.models.context import ContextItem
from opencontext_core.retrieval.contracts import EvidenceItem
from opencontext_core.rules.loader import (
    RulesConfig,
    RulesLoader,
)
from opencontext_core.safety.firewall import ContextFirewall


def _config() -> OpenContextConfig:
    return OpenContextConfig.model_validate(default_config_data())


class TestDiscoveryAndDedup:
    def test_single_loader_returns_deduplicated_rules_with_provenance(self, tmp_path: Path) -> None:
        # AGENTS.md is matched by BOTH AgentHintsManager.HINTS_FILES and
        # instructions.SOURCES; the unified loader must represent it exactly once.
        (tmp_path / "AGENTS.md").write_text(
            "# Proj\n\n## Conventions\n- Prefer dataclasses over dicts\n",
            encoding="utf-8",
        )
        rules_dir = tmp_path / ".opencontext" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "style.md").write_text("Use four-space indentation\n", encoding="utf-8")

        loader = RulesLoader(RulesConfig())
        resolved = loader.resolve(project_root=tmp_path)

        # Exactly one rule record per physical file.
        files = [rule.source_file for rule in resolved.applied]
        agents_files = [f for f in files if f.name == "AGENTS.md"]
        assert len(set(agents_files)) == 1
        # AGENTS.md must not appear twice from two parsers.
        assert agents_files.count(agents_files[0]) == 1

        # Both files contributed.
        names = {f.name for f in files}
        assert "AGENTS.md" in names
        assert "style.md" in names

        # Each rule exposes its originating source path.
        for rule in resolved.applied:
            assert rule.source_file.exists()

    def test_rules_carry_category_provenance(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text(
            "# Proj\n\n## Warnings\n- Never commit secrets\n",
            encoding="utf-8",
        )
        loader = RulesLoader(RulesConfig())
        resolved = loader.resolve(project_root=tmp_path)
        categories = {rule.category for rule in resolved.applied}
        assert "warnings" in categories


class TestConsolidation:
    def test_loader_covers_both_legacy_discovery_surfaces(self, tmp_path: Path) -> None:
        # A file unique to AgentHintsManager.HINTS_FILES (.opencontexthints) and
        # a file unique to instructions.SOURCES (.clinerules) must both be
        # discovered by the single consolidated loader.
        (tmp_path / ".opencontexthints").write_text(
            "project: P\n\n[conventions]\n- hints_rule\n", encoding="utf-8"
        )
        (tmp_path / ".clinerules").write_text("cline_rule\n", encoding="utf-8")

        resolved = RulesLoader(RulesConfig()).resolve(project_root=tmp_path)
        contents = [r.content for r in resolved.applied]
        assert "hints_rule" in contents
        assert "cline_rule" in contents
        # Both surfaces flow through one resolution result (one loader call).
        files = {r.source_file.name for r in resolved.applied}
        assert {".opencontexthints", ".clinerules"} <= files

    def test_loader_reuses_agent_hints_parser(self) -> None:
        # The loader must reuse the existing parser, not a third parser.
        from opencontext_core.dx.agent_hints import AgentHintsManager

        loader = RulesLoader(RulesConfig())
        assert isinstance(loader._parser, AgentHintsManager)


class TestLayeredResolution:
    def test_project_layer_overrides_global_for_same_key(self, tmp_path: Path) -> None:
        global_root = tmp_path / "home"
        project_root = tmp_path / "proj"
        global_root.mkdir()
        project_root.mkdir()

        (global_root / ".opencontexthints").write_text(
            "project: G\n\n[conventions]\n- line_length=80\n",
            encoding="utf-8",
        )
        (project_root / ".opencontexthints").write_text(
            "project: P\n\n[conventions]\n- line_length=120\n",
            encoding="utf-8",
        )

        loader = RulesLoader(RulesConfig())
        resolved = loader.resolve(project_root=project_root, global_root=global_root)

        applied_contents = [r.content for r in resolved.applied]
        assert "line_length=120" in applied_contents
        assert "line_length=80" not in applied_contents

        # The overridden global value is recorded, not silently dropped.
        overridden_contents = [r.content for r in resolved.overridden]
        assert "line_length=80" in overridden_contents
        # And the override record links winner to the layer that won.
        winner = next(r for r in resolved.applied if r.content == "line_length=120")
        assert winner.layer == "project"
        loser = next(r for r in resolved.overridden if r.content == "line_length=80")
        assert loser.layer == "global"

    def test_disabling_a_layer_excludes_its_rules(self, tmp_path: Path) -> None:
        global_root = tmp_path / "home"
        project_root = tmp_path / "proj"
        global_root.mkdir()
        project_root.mkdir()

        (global_root / ".opencontexthints").write_text(
            "project: G\n\n[conventions]\n- global_only_rule\n",
            encoding="utf-8",
        )
        (project_root / ".opencontexthints").write_text(
            "project: P\n\n[conventions]\n- project_rule\n",
            encoding="utf-8",
        )

        cfg = RulesConfig(enabled_layers=("project", "change"))
        loader = RulesLoader(cfg)
        resolved = loader.resolve(project_root=project_root, global_root=global_root)

        contents = [r.content for r in resolved.applied]
        assert "global_only_rule" not in contents
        assert "project_rule" in contents

    def test_invalid_precedence_layer_is_rejected(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            RulesConfig(precedence=("global", "bogus", "change"))


class TestEvidenceConversion:
    def test_rule_converts_to_evidence_item_with_rule_source_type(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / ".opencontext" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "style.md").write_text("Prefer dataclasses over dicts\n", encoding="utf-8")

        loader = RulesLoader(RulesConfig())
        resolved = loader.resolve(project_root=tmp_path)
        evidence = loader.to_evidence(resolved, project_root=tmp_path)

        assert evidence, "expected at least one rule evidence item"
        item = evidence[0]
        assert isinstance(item, EvidenceItem)
        assert item.source_type == "rule"
        assert item.id
        assert "file" in item.provenance
        assert "layer" in item.provenance
        assert "category" in item.provenance
        # Provenance file points at style.md and layer is project.
        assert "style.md" in str(item.provenance["file"])
        assert item.provenance["layer"] == "project"


class TestFirewallScan:
    def test_rule_evidence_with_secret_is_redacted_by_firewall(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / ".opencontext" / "rules"
        rules_dir.mkdir(parents=True)
        # A raw secret-looking value inside a rule file.
        secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        (rules_dir / "leak.md").write_text(f"Use this key {secret} for tests\n", encoding="utf-8")

        loader = RulesLoader(RulesConfig())
        resolved = loader.resolve(project_root=tmp_path)
        evidence = loader.to_evidence(resolved, project_root=tmp_path)
        items: list[ContextItem] = loader.evidence_to_context_items(evidence)

        firewall = ContextFirewall(_config())
        decision = firewall.check_context_export(items, sink="context_pack")
        # Redact-and-continue: the export is allowed but the raw secret is stripped
        # from every exported item rather than hard-failing the pack.
        assert decision.allowed is True
        assert all(secret not in item.content for item in items)


class TestSkipAndFailSafe:
    def test_malformed_file_is_skipped_request_still_succeeds(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text(
            "# Proj\n\n## Conventions\n- valid rule here\n", encoding="utf-8"
        )
        # A rule file whose bytes cannot be decoded as UTF-8 text.
        bad = tmp_path / ".clinerules"
        bad.write_bytes(b"\xff\xfe\x00\x00bad bytes")

        loader = RulesLoader(RulesConfig())
        resolved = loader.resolve(project_root=tmp_path)

        contents = [r.content for r in resolved.applied]
        assert "valid rule here" in contents
        # The malformed file is recorded as skipped with a reason.
        assert any(".clinerules" in str(s.source_file) for s in resolved.skipped)
        assert all(s.reason for s in resolved.skipped)
