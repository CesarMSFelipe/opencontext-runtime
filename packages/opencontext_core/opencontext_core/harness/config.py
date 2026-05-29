"""Harness configuration — mapping workflow phases to budgets and gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PhaseConfig:
    """Configuration for a single workflow phase."""

    budget_tokens: int = 6000
    gates: list[str] = field(default_factory=list)
    confidence_threshold: float | None = None


@dataclass
class HarnessConfig:
    """Complete harness configuration loaded from .opencontext/harness.yaml."""

    version: str = "0.1"
    budget_mode: str = "warn"
    artifact_root: str = ".opencontext/runs"
    phases: dict[str, PhaseConfig] = field(
        default_factory=lambda: {
            "explore": PhaseConfig(
                budget_tokens=6000,
                gates=[
                    "project_index_exists",
                    "context_pack_created",
                    "no_secret_leakage",
                ],
            ),
            "propose": PhaseConfig(
                budget_tokens=6000,
                gates=[
                    "trace_id_created",
                    "included_sources_present",
                    "omissions_recorded",
                ],
            ),
            "apply": PhaseConfig(
                budget_tokens=12000,
                confidence_threshold=0.4,
                gates=[
                    "provider_policy_passed",
                    "approval_required_for_writes",
                ],
            ),
            "verify": PhaseConfig(
                budget_tokens=4000,
                confidence_threshold=0.3,
                gates=[
                    "security_scan_passed",
                    "no_high_risk_exports",
                ],
            ),
            "review": PhaseConfig(
                budget_tokens=4000,
                confidence_threshold=0.3,
                gates=[
                    "review_artifact_created",
                ],
            ),
            "archive": PhaseConfig(
                budget_tokens=2000,
                gates=[
                    "trace_persisted",
                    "memory_delta_created",
                    "graph_delta_created",
                ],
            ),
        }
    )
    active_clients: list[str] = field(default_factory=lambda: ["opencode"])
    default_client: str = "opencode"
    orchestrator_mode: str = "multi-phase"
    forbidden_paths: list[str] = field(
        default_factory=lambda: [
            ".env",
            "secrets/",
            "private/",
            "vendor/",
            "node_modules/",
        ]
    )
    forbidden_commands: list[str] = field(
        default_factory=lambda: [
            "rm -rf",
            "git push --force",
            "curl | bash",
        ]
    )

    @classmethod
    def from_yaml_file(cls, path: Path) -> HarnessConfig:
        """Load harness config from a YAML file, falling back to defaults."""
        import yaml

        if not path.exists():
            return cls()

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return cls()

        if not isinstance(data, dict):
            return cls()

        config = cls()
        config.version = data.get("version", config.version)
        wf_defaults = data.get("workflow_defaults", {})
        if isinstance(wf_defaults, dict):
            config.budget_mode = wf_defaults.get("budget_mode", config.budget_mode)
            config.artifact_root = wf_defaults.get("artifact_root", config.artifact_root)

        phases_data = data.get("phases", {})
        if isinstance(phases_data, dict):
            for phase_name, phase_cfg in phases_data.items():
                if isinstance(phase_cfg, dict):
                    config.phases[phase_name] = PhaseConfig(
                        budget_tokens=phase_cfg.get("budget_tokens", 6000),
                        gates=phase_cfg.get("gates", []),
                    )

        agents_data = data.get("agents", {})
        if isinstance(agents_data, dict):
            config.active_clients = agents_data.get("active_clients", config.active_clients)
            config.default_client = agents_data.get("default_client", config.default_client)
            config.orchestrator_mode = agents_data.get("mode", config.orchestrator_mode)

        safety = data.get("safety", {})
        if isinstance(safety, dict):
            config.forbidden_paths = safety.get("forbidden_paths", config.forbidden_paths)
            config.forbidden_commands = safety.get("forbidden_commands", config.forbidden_commands)

        return config
