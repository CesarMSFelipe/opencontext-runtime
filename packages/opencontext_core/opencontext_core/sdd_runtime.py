"""Local SDD/TDD runtime helpers.

This module is deliberately provider-neutral. It detects local verification
capabilities and writes small project artifacts that agents can consume without
reading the whole repository.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class TestCapability(BaseModel):
    """Detected local test or validation command."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stable capability name.")
    command: list[str] = Field(description="Command tokens to run the capability.")
    evidence: str = Field(description="File or convention that caused detection.")
    scope: str = Field(default="focused", description="focused, broad, lint, type, or e2e.")


class SDDContext(BaseModel):
    """Project-local SDD/TDD context written during initialization."""

    model_config = ConfigDict(extra="forbid")

    root: str = Field(description="Resolved project root.")
    strict_tdd: bool = Field(description="Whether a test harness was detected.")
    tdd_mode: str = Field(default="ask", description="ask, strict, or off user preference.")
    phases: list[str] = Field(description="SDD lifecycle phases.")
    test_capabilities: list[TestCapability] = Field(description="Detected verification commands.")
    token_budget_per_phase: int = Field(ge=1, description="Default context token budget per phase.")
    instructions: list[str] = Field(description="Compact agent instructions for SDD/TDD runs.")
    active_clients: list[str] = Field(
        default_factory=list,
        description="Agent clients configured during setup.",
    )
    orchestrator_profiles: dict[str, str] = Field(
        default_factory=dict,
        description="Map of client → orchestrator_type for configured clients.",
    )
    sdd_model_profile: str = Field(
        default="default",
        description="SDD model profile (default, cheap, hybrid, premium).",
    )


SDD_PHASES: list[str] = [
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "archive",
]


def detect_test_capabilities(root: Path | str) -> list[TestCapability]:
    """Detect local test and validation commands without executing them."""

    base = Path(root)
    capabilities: list[TestCapability] = []

    if (base / "pyproject.toml").exists() or (base / "pytest.ini").exists():
        capabilities.append(
            TestCapability(
                name="pytest",
                command=["pytest"],
                evidence="pyproject.toml or pytest.ini",
                scope="focused",
            )
        )
    if (base / "ruff.toml").exists() or (base / "pyproject.toml").exists():
        capabilities.append(
            TestCapability(
                name="ruff-check",
                command=["ruff", "check", "."],
                evidence="ruff.toml or pyproject.toml",
                scope="lint",
            )
        )
    if (base / "mypy.ini").exists() or _pyproject_mentions(base, "mypy"):
        capabilities.append(
            TestCapability(
                name="mypy",
                command=["mypy"],
                evidence="mypy.ini or pyproject.toml",
                scope="type",
            )
        )
    if (base / "package.json").exists():
        capabilities.extend(_package_json_capabilities(base / "package.json"))
    if (base / "go.mod").exists():
        capabilities.append(
            TestCapability(
                name="go-test",
                command=["go", "test", "./..."],
                evidence="go.mod",
                scope="focused",
            )
        )
    if (base / "Cargo.toml").exists():
        capabilities.append(
            TestCapability(
                name="cargo-test",
                command=["cargo", "test"],
                evidence="Cargo.toml",
                scope="focused",
            )
        )

    return _dedupe_capabilities(capabilities)


def build_sdd_context(
    root: Path | str,
    *,
    token_budget_per_phase: int = 3000,
    tdd_mode: str = "ask",
    active_clients: list[str] | None = None,
    sdd_model_profile: str = "default",
) -> SDDContext:
    """Build a compact SDD/TDD context model for a project."""

    from opencontext_core.sdd_profiles import get_client_orchestrator_profile

    resolved = Path(root).resolve()
    capabilities = detect_test_capabilities(resolved)
    strict_tdd = any(item.scope in {"focused", "e2e"} for item in capabilities)
    normalized_tdd_mode = tdd_mode if tdd_mode in {"ask", "strict", "off"} else "ask"
    clients = active_clients or []
    orchestrator_profiles = {
        c: get_client_orchestrator_profile(c).orchestrator_type for c in clients
    }
    instructions = [
        "Read `.opencontext/sdd/context.json` at the start of every task.",
        'Query the knowledge graph (`opencontext kg query "<task>"`) before reading source files.',
        'Use `opencontext pack . --query "<task>" --max-tokens <budget> --mode plan` '
        "instead of reading broad file sets.",
        "Keep each SDD phase under the configured token budget unless explicitly overridden.",
        "During verify, run focused tests first, then broader lint/type checks when available.",
        "Persist decisions, omitted context reasons, trace ids, and verification evidence.",
    ]
    if normalized_tdd_mode == "ask":
        instructions.append(
            "Before apply, ask whether this change should use TDD; "
            "recommend yes when a harness exists."
        )
    elif normalized_tdd_mode == "strict":
        instructions.append(
            "During apply, write or update the closest failing test before implementation."
        )
    else:
        instructions.append(
            "TDD is optional for this project; do not block apply solely on tests-first."
        )
    if not strict_tdd:
        instructions.append(
            "No test harness was detected; propose the smallest test harness before apply."
        )

    return SDDContext(
        root=str(resolved),
        strict_tdd=strict_tdd,
        tdd_mode=normalized_tdd_mode,
        phases=list(SDD_PHASES),
        test_capabilities=capabilities,
        token_budget_per_phase=token_budget_per_phase,
        instructions=instructions,
        active_clients=clients,
        orchestrator_profiles=orchestrator_profiles,
        sdd_model_profile=sdd_model_profile,
    )


def write_sdd_context(
    root: Path | str,
    *,
    token_budget_per_phase: int = 3000,
    tdd_mode: str = "ask",
    active_clients: list[str] | None = None,
    sdd_model_profile: str = "default",
) -> tuple[SDDContext, list[Path]]:
    """Write project-local SDD/TDD artifacts and return their paths."""

    base = Path(root)
    context = build_sdd_context(
        base,
        token_budget_per_phase=token_budget_per_phase,
        tdd_mode=tdd_mode,
        active_clients=active_clients,
        sdd_model_profile=sdd_model_profile,
    )
    out_dir = base / ".opencontext" / "sdd"
    out_dir.mkdir(parents=True, exist_ok=True)

    context_path = out_dir / "context.json"
    testing_path = out_dir / "testing.md"
    context_path.write_text(
        json.dumps(context.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    testing_path.write_text(_render_testing_markdown(context), encoding="utf-8")
    return context, [context_path, testing_path]


def phase_token_ledger(context: SDDContext, used_tokens: int = 0) -> list[dict[str, int | str]]:
    """Build a per-phase token ledger for SDD reporting."""

    return [
        {
            "phase": phase,
            "budget": context.token_budget_per_phase,
            "used": used_tokens if phase in {"explore", "propose"} else 0,
            "remaining": max(
                context.token_budget_per_phase
                - (used_tokens if phase in {"explore", "propose"} else 0),
                0,
            ),
        }
        for phase in context.phases
    ]


def _pyproject_mentions(root: Path, text: str) -> bool:
    path = root / "pyproject.toml"
    if not path.exists():
        return False
    return text in path.read_text(encoding="utf-8", errors="ignore").lower()


def _package_json_capabilities(path: Path) -> list[TestCapability]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    if not isinstance(scripts, dict):
        return []
    capabilities: list[TestCapability] = []
    for script_name, scope in (
        ("test", "focused"),
        ("lint", "lint"),
        ("typecheck", "type"),
        ("e2e", "e2e"),
    ):
        if script_name in scripts:
            capabilities.append(
                TestCapability(
                    name=f"npm-{script_name}",
                    command=["npm", "run", script_name],
                    evidence=f"package.json scripts.{script_name}",
                    scope=scope,
                )
            )
    return capabilities


def _dedupe_capabilities(items: list[TestCapability]) -> list[TestCapability]:
    seen: set[str] = set()
    unique: list[TestCapability] = []
    for item in items:
        key = " ".join(item.command)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _render_testing_markdown(context: SDDContext) -> str:
    lines = [
        "# OpenContext SDD/TDD Context",
        "",
        f"Strict TDD available: `{str(context.strict_tdd).lower()}`",
        f"TDD mode: `{context.tdd_mode}`",
        f"Token budget per phase: `{context.token_budget_per_phase}`",
        f"SDD model profile: `{context.sdd_model_profile}`",
        "",
        "## Test capabilities",
    ]
    if context.test_capabilities:
        for item in context.test_capabilities:
            lines.append(f"- `{' '.join(item.command)}` — {item.scope}; evidence: {item.evidence}")
    else:
        lines.append("- No local test harness detected yet.")
    if context.orchestrator_profiles:
        lines.extend(["", "## Client orchestrator profiles"])
        for client, orch_type in context.orchestrator_profiles.items():
            lines.append(f"- **{client}**: `{orch_type}`")
    lines.extend(["", "## Agent rules"])
    lines.extend(f"- {instruction}" for instruction in context.instructions)
    return "\n".join(lines) + "\n"
