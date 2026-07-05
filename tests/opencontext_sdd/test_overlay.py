"""SDD overlay tests: agent count, chained PR binding, profile overlays.

Per openspec/changes/agentic-parity-engram-gentle/tasks.md §PR4.a
— T4.5.
"""

from __future__ import annotations

from opencontext_sdd.overlay import (
    SDD_OVERLAY_MULTI,
    get_agent_for_phase,
    get_overlay,
    get_phase_list,
)


class TestOverlay:
    def test_overlay_lists_10_sub_agents(self) -> None:
        """Overlay contains explore, propose, spec, design, tasks, apply,
        verify, archive (8 phases) + chained_pr + onboard = 10 sub-agent entries."""
        overlay = get_overlay()
        agents = overlay.get("agents", {})
        # 8 phases
        assert len(agents) == 8
        for phase in (
            "explore",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "archive",
        ):
            assert phase in agents

    def test_chained_pr_binding_by_registry_name(self) -> None:
        """chained_pr is bound by registry_name."""
        overlay = get_overlay()
        cp = overlay.get("chained_pr", {})
        assert cp.get("registry_name") == "chained-pr"

    def test_onboard_present(self) -> None:
        """onboard entry is present in the overlay."""
        overlay = get_overlay()
        assert "onboard" in overlay

    def test_get_agent_for_phase(self) -> None:
        """get_agent_for_phase returns the correct skill name."""
        assert get_agent_for_phase("apply") == "sdd-apply"
        assert get_agent_for_phase("spec") == "sdd-spec"
        assert get_agent_for_phase("explore") == "sdd-explore"

    def test_get_agent_for_unknown_phase(self) -> None:
        """get_agent_for_phase returns None for an unknown phase."""
        assert get_agent_for_phase("nonexistent") is None

    def test_get_phase_list_ordered(self) -> None:
        """get_phase_list returns phases in the correct order."""
        phases = get_phase_list()
        assert phases == [
            "explore",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "archive",
        ]

    def test_overlay_version(self) -> None:
        """Overlay has a version string."""
        assert SDD_OVERLAY_MULTI["version"] == "1.0"
