"""Skill v2 audit — Tier 0 validation, persona/skill mismatches, secret leak detection (A6)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

Severity = Literal["INFO", "WARN", "ERROR"]

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)password\s*[:=]\s*['\"]?[^\s'\"#]{8,}"),
)

_PERSONA_ALLOWLIST: frozenset[str] = frozenset(
    {
        "senior-architect",
        "reviewer",
        "explorer",
        "scribe",
        "lazy-dev",
    }
)


@dataclass(frozen=True)
class AuditFinding:
    severity: Severity
    code: str
    message: str


@dataclass
class AuditReport:
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "WARN"]


class SkillAudit:
    """Static audit over a directory of skill YAML files."""

    def run(self, root: Path) -> AuditReport:
        report = AuditReport()
        if not root.exists():
            report.findings.append(
                AuditFinding(severity="ERROR", code="root_missing", message=f"root missing: {root}")
            )
            return report
        skills: list[tuple[Path, dict[str, object]]] = []
        for yaml_file in sorted(root.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                report.findings.append(
                    AuditFinding(
                        severity="ERROR",
                        code="yaml_parse",
                        message=f"{yaml_file.name}: {exc}",
                    )
                )
                continue
            if not isinstance(data, dict):
                report.findings.append(
                    AuditFinding(
                        severity="ERROR",
                        code="shape",
                        message=f"{yaml_file.name}: not a mapping",
                    )
                )
                continue
            self._check_one(yaml_file, data, report)
            skills.append((yaml_file, data))
        self._check_confusables(skills, report)
        return report

    def _check_one(
        self, path: Path, data: dict[str, object], report: AuditReport
    ) -> None:
        # required fields
        for field_name in ("tier", "required_capabilities", "persona_compat", "contract"):
            if field_name not in data:
                report.findings.append(
                    AuditFinding(
                        severity="ERROR",
                        code="missing_field",
                        message=f"{path.name}: missing {field_name!r}",
                    )
                )
        if data.get("tier") not in (0, 1, 2, 3):
            report.findings.append(
                AuditFinding(
                    severity="ERROR",
                    code="tier",
                    message=f"{path.name}: invalid tier {data.get('tier')!r}",
                )
            )
        personas_raw = data.get("persona_compat") or []
        personas: list[object] = personas_raw if isinstance(personas_raw, list) else [personas_raw]
        for persona in personas:
            if not isinstance(persona, str) or persona not in _PERSONA_ALLOWLIST:
                report.findings.append(
                    AuditFinding(
                        severity="WARN",
                        code="persona_mismatch",
                        message=f"{path.name}: persona {persona!r} not in allow-list",
                    )
                )
        # secret detection
        text = path.read_text(encoding="utf-8")
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                report.findings.append(
                    AuditFinding(
                        severity="ERROR",
                        code="secret_leak",
                        message=f"{path.name}: potential secret detected ({pat.pattern})",
                    )
                )
                break

    @staticmethod
    def _check_confusables(
        skills: list[tuple[Path, dict[str, object]]], report: AuditReport
    ) -> None:
        seen: dict[str, str] = {}
        for path, data in skills:
            raw_id = data.get("id", "")
            sid = str(raw_id).lower() if raw_id is not None else ""
            if not sid:
                continue
            if sid in seen and seen[sid] != path.name:
                report.findings.append(
                    AuditFinding(
                        severity="WARN",
                        code="confusable_id",
                        message=f"{path.name} shares id {sid!r} with {seen[sid]}",
                    )
                )
            else:
                seen[sid] = path.name


__all__ = ["AuditFinding", "AuditReport", "Severity", "SkillAudit"]
