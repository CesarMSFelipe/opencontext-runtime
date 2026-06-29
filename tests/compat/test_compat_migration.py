"""Migration ledger + the 4-condition "migrated" predicate (SPEC CL-006/008/011)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.compat import (
    MIGRATION_LEDGER,
    TWO_SPINE_CONVERGENCE,
    MigrationLedger,
    MigrationState,
    ModuleMigration,
    direct_legacy_importers,
    is_migrated,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestMigrationState:
    def test_has_exactly_four_members(self) -> None:
        assert {s.value for s in MigrationState} == {"legacy", "adapted", "migrated", "removed"}


class TestRoundTrip:
    def test_module_migration_round_trips(self) -> None:
        entry = ModuleMigration(
            module="harness/runner.py",
            legacy_symbol="HarnessRunner",
            state=MigrationState.adapted,
            superseded_by="PR-003",
            removal_milestone="milestone-C",
            flag="runtime.registry_enabled",
        )
        reloaded = ModuleMigration.model_validate_json(entry.model_dump_json())
        assert reloaded.state is MigrationState.adapted
        assert reloaded.superseded_by == "PR-003"
        assert reloaded.removal_milestone == "milestone-C"
        assert reloaded.flag == "runtime.registry_enabled"

    def test_ledger_round_trips(self) -> None:
        reloaded = MigrationLedger.model_validate_json(MIGRATION_LEDGER.model_dump_json())
        assert reloaded.states() == MIGRATION_LEDGER.states()
        assert reloaded.convergence.chosen_spine == "HarnessRunner->RuntimeApi"


class TestSeededLedger:
    def test_every_spec_named_module_is_classified(self) -> None:
        # CL-002/003/004/007/008 modules each resolve to exactly one state.
        expected = {
            "harness/runner.py",
            "oc_new/conductor.py",
            "agents/sdd_orchestrator.py",
            "llm/sampling_gateway.py",
            "llm/provider_gateway.py",
            "safety/firewall.py",
            "retrieval/planner.py",
            "context/packing.py",
        }
        states = MIGRATION_LEDGER.states()
        assert expected.issubset(states.keys())
        for module in expected:
            assert isinstance(states[module], MigrationState)

    def test_no_duplicate_module(self) -> None:
        modules = [e.module for e in MIGRATION_LEDGER.modules]
        assert len(modules) == len(set(modules))

    def test_pending_subsystems_are_legacy(self) -> None:
        # PR-010/012 have not shipped -> their modules stay legacy.
        assert MIGRATION_LEDGER.get("retrieval/planner.py").state is MigrationState.legacy
        assert MIGRATION_LEDGER.get("llm/provider_gateway.py").state is MigrationState.legacy

    def test_to_markdown_lists_rows(self) -> None:
        md = MIGRATION_LEDGER.to_markdown()
        assert "| Module | Legacy symbol | State |" in md
        assert "harness/runner.py" in md
        assert "HarnessRunner" in md


class TestTwoSpineConvergence:
    def test_chosen_spine_is_harness_runner(self) -> None:
        assert TWO_SPINE_CONVERGENCE.chosen_spine == "HarnessRunner->RuntimeApi"
        assert TWO_SPINE_CONVERGENCE.adapted_spine == "OcNewConductor"
        assert TWO_SPINE_CONVERGENCE.adapted_spine_state is MigrationState.adapted
        assert TWO_SPINE_CONVERGENCE.removal_milestone


class TestIsMigratedPredicate:
    def _all_conditions_met_entry(self) -> ModuleMigration:
        # A symbol nothing imports, with parity recorded -> all 4 conditions pass.
        return ModuleMigration(
            module="fake/never.py",
            legacy_symbol="ZzzNeverImportedSymbol",
            state=MigrationState.migrated,
            vnext_only=True,
            legacy_shimmed=True,
            parity_test="tests/compat/test_compat_migration.py",
        )

    def test_all_four_conditions_true_is_migrated(self) -> None:
        ledger = MigrationLedger(modules=[self._all_conditions_met_entry()])
        migrated, reasons = ledger.is_migrated("fake/never.py", root=REPO_ROOT)
        assert migrated is True
        assert reasons == []

    def test_condition_a_failure_named(self) -> None:
        entry = self._all_conditions_met_entry()
        entry.vnext_only = False
        ledger = MigrationLedger(modules=[entry])
        migrated, reasons = ledger.is_migrated("fake/never.py", root=REPO_ROOT)
        assert migrated is False
        assert any(r.startswith("(a)") for r in reasons)

    def test_condition_b_failure_named(self) -> None:
        entry = self._all_conditions_met_entry()
        entry.legacy_shimmed = False
        ledger = MigrationLedger(modules=[entry])
        migrated, reasons = ledger.is_migrated("fake/never.py", root=REPO_ROOT)
        assert migrated is False
        assert any(r.startswith("(b)") for r in reasons)

    def test_condition_c_failure_named(self) -> None:
        entry = self._all_conditions_met_entry()
        entry.parity_test = None
        ledger = MigrationLedger(modules=[entry])
        migrated, reasons = ledger.is_migrated("fake/never.py", root=REPO_ROOT)
        assert migrated is False
        assert any(r.startswith("(c)") for r in reasons)

    def test_condition_d_failure_on_real_import(self) -> None:
        # HarnessRunner is the live spine -> imported widely -> condition (d) fails.
        migrated, reasons = is_migrated("harness/runner.py")
        assert migrated is False
        assert any(r.startswith("(d)") for r in reasons)

    def test_unknown_module_not_migrated(self) -> None:
        migrated, reasons = is_migrated("does/not/exist.py")
        assert migrated is False
        assert reasons


class TestDirectLegacyImporters:
    def test_finds_importer_and_skips_others(self, tmp_path: Path) -> None:
        (tmp_path / "legacymod.py").write_text("class Foo:\n    pass\n", encoding="utf-8")
        (tmp_path / "consumer.py").write_text(
            "from pkg.legacymod import Foo\n\n_ = Foo\n", encoding="utf-8"
        )
        (tmp_path / "unrelated.py").write_text("x = 1\n", encoding="utf-8")

        importers = direct_legacy_importers("legacymod.py", "Foo", package_root=tmp_path)

        assert importers == ["consumer.py"]

    def test_skips_compat_package(self, tmp_path: Path) -> None:
        compat = tmp_path / "compat"
        compat.mkdir()
        (compat / "ref.py").write_text("from pkg.legacymod import Foo\n", encoding="utf-8")
        importers = direct_legacy_importers("legacymod.py", "Foo", package_root=tmp_path)
        assert importers == []
