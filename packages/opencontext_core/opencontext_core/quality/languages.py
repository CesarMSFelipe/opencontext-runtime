"""Per-language code-quality runner for the architecture & quality feature.

This module orchestrates each language's real tooling (linters, type checkers,
formatters) over the *changed* files and normalizes their output into the shared
:class:`~opencontext_core.quality.models.Finding` type. It is deterministic and
makes **zero model calls** — the only side effect is running the configured
tools as subprocesses (a wall-clock cost, not a token cost).

It mirrors ``VerifyPhase._run_tests``'s subprocess model exactly: a shell-free
``argv`` list, captured stdout/stderr/exit code, and a wall-clock timeout. There
is no ``SafeCommand`` executor in the codebase (``SafeCommand`` is a declarative
spec nothing runs), so this builds its own minimal, safe execution.

Honest degradation is a hard rule:

* a **missing required** tool (one declared ``required_in`` the active profile)
  produces a ``tool_missing`` ERROR finding — never a silent pass;
* a **missing optional** tool is recorded in the returned ``skipped`` tuple;
* a tool that is unavailable is *reported*, never silently treated as clean.

The registry is seeded from the curated standards each first-party profile
already declares (``ruff``/``mypy``/``eslint``/``gofmt``…) and extended to cover
languages whose profiles declare no validation commands (Go, Rust, …) and the
standard tool tiers.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencontext_core.indexing.classifier import detect_language
from opencontext_core.quality.ci_checks import CheckSeverity
from opencontext_core.quality.models import Finding
from opencontext_core.quality.rules import LanguageRule, StandardsProfile

# Sentinels for the subprocess exit code (mirror VerifyPhase._run_tests).
_EXIT_TIMEOUT = -1
_EXIT_MISSING = -2


@dataclass(frozen=True)
class ToolSpec:
    """A single tool invocation recipe for one language/profile tier.

    ``base_argv`` is the shell-free command prefix (e.g. ``('ruff', 'check',
    '--output-format', 'json')``). ``scope_mode`` controls how the changed
    files are applied:

    * ``append_paths`` — append the changed file paths to ``base_argv`` (and
      drop a trailing ``'.'`` so a project-wide command becomes file-scoped);
    * ``whole_project`` — run the command unchanged (the tool walks the project
      itself, e.g. ``go vet ./...``);
    * ``no_args`` — run ``base_argv`` exactly, no path arguments.

    ``parser`` selects the output-to-:class:`Finding` mapper in ``_PARSERS``.
    ``required_in`` lists the profiles where a *missing* tool is an ERROR (a hard
    finding); in every other profile a missing tool is recorded in ``skipped``.
    """

    name: str
    base_argv: tuple[str, ...]
    scope_mode: str  # 'append_paths' | 'whole_project' | 'no_args'
    parser: str
    severity: CheckSeverity = CheckSeverity.WARNING
    required_in: tuple[StandardsProfile, ...] = ()
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolRun:
    """The captured result of running one :class:`ToolSpec`.

    ``missing`` is ``True`` only when the executable was not found
    (``FileNotFoundError`` -> ``exit_code == -2``). A timeout maps to
    ``exit_code == -1`` with ``missing == False`` so the two are distinguishable.
    """

    tool: str
    exit_code: int
    stdout: str
    stderr: str
    missing: bool


# --------------------------------------------------------------------------- #
# Registry: language -> profile tier -> ordered tool specs
# --------------------------------------------------------------------------- #


def _spec(
    name: str,
    base_argv: tuple[str, ...],
    parser: str,
    *,
    languages: tuple[str, ...],
    scope_mode: str = "append_paths",
    severity: CheckSeverity = CheckSeverity.WARNING,
    required_in: tuple[StandardsProfile, ...] = (StandardsProfile.STRICT,),
) -> ToolSpec:
    """Build a :class:`ToolSpec`; defaults make a tool *required* only at STRICT.

    Keeping tools required only in the STRICT tier means the relaxed/standard
    zero-config path never *blocks* on a tool that is not installed — it records
    the absence in ``skipped`` and moves on (degrade honestly).
    """
    return ToolSpec(
        name=name,
        base_argv=base_argv,
        scope_mode=scope_mode,
        parser=parser,
        severity=severity,
        required_in=required_in,
        languages=languages,
    )


# Python: ruff (lint) at every tier; mypy (types) from standard; bandit at strict.
_PY = ("python",)
_PYTHON_RELAXED: tuple[ToolSpec, ...] = (
    _spec("ruff", ("ruff", "check", "--output-format", "json"), "ruff_json", languages=_PY),
)
_PYTHON_STANDARD: tuple[ToolSpec, ...] = (
    *_PYTHON_RELAXED,
    _spec("mypy", ("mypy",), "mypy_text", languages=_PY),
)
_PYTHON_STRICT: tuple[ToolSpec, ...] = (
    *_PYTHON_STANDARD,
    _spec(
        "bandit",
        ("bandit", "-q", "-f", "json"),
        "bandit_json",
        languages=_PY,
        severity=CheckSeverity.ERROR,
    ),
)

# JavaScript / TypeScript: eslint (lint) at every tier; tsc (types) from standard.
_JS = ("javascript",)
_TS = ("typescript",)


def _js_tiers(langs: tuple[str, ...]) -> dict[StandardsProfile, tuple[ToolSpec, ...]]:
    relaxed = (_spec("eslint", ("eslint", "--format", "json"), "eslint_json", languages=langs),)
    standard = (
        *relaxed,
        _spec(
            "tsc",
            ("tsc", "--noEmit"),
            "exit_only",
            languages=langs,
            scope_mode="whole_project",
        ),
    )
    return {
        StandardsProfile.RELAXED: relaxed,
        StandardsProfile.STANDARD: standard,
        StandardsProfile.STRICT: standard,
    }


# Go: gofmt (format check) at every tier; go vet from standard; staticcheck at strict.
_GO = ("go",)
_GO_RELAXED: tuple[ToolSpec, ...] = (_spec("gofmt", ("gofmt", "-l"), "gofmt_list", languages=_GO),)
_GO_STANDARD: tuple[ToolSpec, ...] = (
    *_GO_RELAXED,
    _spec("go", ("go", "vet", "./..."), "exit_only", languages=_GO, scope_mode="whole_project"),
)
_GO_STRICT: tuple[ToolSpec, ...] = (
    *_GO_STANDARD,
    _spec(
        "staticcheck",
        ("staticcheck", "./..."),
        "exit_only",
        languages=_GO,
        scope_mode="whole_project",
    ),
)

# Rust: cargo fmt (format check) at every tier; cargo clippy from standard.
_RS = ("rust",)
_RUST_RELAXED: tuple[ToolSpec, ...] = (
    _spec(
        "cargo-fmt",
        ("cargo", "fmt", "--", "--check"),
        "exit_only",
        languages=_RS,
        scope_mode="no_args",
    ),
)
_RUST_STANDARD: tuple[ToolSpec, ...] = (
    *_RUST_RELAXED,
    _spec(
        "cargo-clippy",
        ("cargo", "clippy", "--quiet"),
        "exit_only",
        languages=_RS,
        scope_mode="no_args",
    ),
)


#: Canonical registry: language -> profile tier -> ordered tool specs.
#: Tiers are nested supersets (relaxed ⊆ standard ⊆ strict).
LANGUAGE_TOOLS: dict[str, dict[StandardsProfile, tuple[ToolSpec, ...]]] = {
    "python": {
        StandardsProfile.RELAXED: _PYTHON_RELAXED,
        StandardsProfile.STANDARD: _PYTHON_STANDARD,
        StandardsProfile.STRICT: _PYTHON_STRICT,
    },
    "javascript": _js_tiers(_JS),
    "typescript": _js_tiers(_TS),
    "go": {
        StandardsProfile.RELAXED: _GO_RELAXED,
        StandardsProfile.STANDARD: _GO_STANDARD,
        StandardsProfile.STRICT: _GO_STRICT,
    },
    "rust": {
        StandardsProfile.RELAXED: _RUST_RELAXED,
        StandardsProfile.STANDARD: _RUST_STANDARD,
        StandardsProfile.STRICT: _RUST_STANDARD,
    },
}


#: Extension fallback for languages ``classifier.LANGUAGE_BY_EXTENSION`` lacks.
_EXT_LANGUAGE: dict[str, str] = {
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".kt": "kotlin",
}


class LanguageStandards:
    """Static resolver over :data:`LANGUAGE_TOOLS` (no instance state)."""

    @staticmethod
    def tools_for(language: str, profile: StandardsProfile) -> tuple[ToolSpec, ...]:
        """Return the ordered tool set for ``language`` at ``profile``.

        Returns ``()`` for an unknown language (degrade honestly — there is no
        tooling to run, and that is recorded by the caller as skipped).
        """
        tiers = LANGUAGE_TOOLS.get(language)
        if not tiers:
            return ()
        return tiers.get(profile, tiers.get(StandardsProfile.STANDARD, ()))

    @staticmethod
    def profile_for(
        language: str,
        rules_languages: tuple[LanguageRule, ...],
        default: StandardsProfile = StandardsProfile.STANDARD,
    ) -> StandardsProfile:
        """Resolve the strictness profile for ``language``.

        Honors an explicit per-language rule if present, else ``default``.
        """
        for rule in rules_languages:
            if rule.language == language:
                return rule.profile
        return default


class LanguageQualityRunner:
    """Runs the per-language tool set over changed files and yields Findings."""

    def __init__(self, root: Path, *, timeout: int = 120) -> None:
        self.root = Path(root)
        self.timeout = timeout

    # -- public API -------------------------------------------------------- #

    def run(
        self,
        changed_files: list[str],
        rules_languages: tuple[LanguageRule, ...],
        *,
        default_profile: StandardsProfile = StandardsProfile.STANDARD,
    ) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
        """Evaluate ``changed_files`` and return ``(findings, skipped)``.

        Files are grouped by language (via :func:`detect_language` plus the
        ``.go``/``.rs``/… extension fallback). For each ``(language, files)``
        group the profile is resolved, its tool set is run scoped to those
        files, and each tool's output is normalized into a
        ``Finding(category='language')``. A missing *required* tool yields a
        ``tool_missing`` ERROR finding; a missing optional tool is recorded in
        ``skipped``. Ordering is fully deterministic (languages, files, and
        tools are all sorted), so the same inputs always produce the same
        result.
        """
        groups = self._group_by_language(changed_files)

        findings: list[Finding] = []
        skipped: list[str] = []

        for language in sorted(groups):
            files = sorted(groups[language])
            profile = LanguageStandards.profile_for(
                language, rules_languages, default=default_profile
            )
            specs = LanguageStandards.tools_for(language, profile)
            if not specs:
                # A language we can detect but have no tooling for: record it,
                # never report it as clean.
                skipped.append(f"{language}:no-tooling")
                continue
            for spec in sorted(specs, key=lambda s: s.name):
                run = self._run_tool(spec, files)
                if run.missing:
                    if profile in spec.required_in:
                        findings.append(self._tool_missing_finding(spec, files))
                    else:
                        skipped.append(f"{language}:{spec.name}:missing")
                    continue
                findings.extend(self._parse(spec, run))

        return tuple(findings), tuple(skipped)

    # -- internals --------------------------------------------------------- #

    def _group_by_language(self, changed_files: list[str]) -> dict[str, list[str]]:
        """Bucket changed files by detected language (POSIX-normalized paths)."""
        groups: dict[str, list[str]] = {}
        for raw in changed_files:
            rel = Path(raw).as_posix()
            language = self._language_of(rel)
            if language is None:
                continue
            groups.setdefault(language, []).append(rel)
        return groups

    @staticmethod
    def _language_of(rel: str) -> str | None:
        """Detect the language for a path, with the extension fallback.

        Returns the language only when it has a configured tool set (otherwise
        there is nothing to run); an unmapped extension returns ``None``.
        """
        path = Path(rel)
        language = detect_language(path)
        if language == "unknown":
            language = _EXT_LANGUAGE.get(path.suffix.lower(), "unknown")
        return language if language in LANGUAGE_TOOLS else None

    def _argv_for(self, spec: ToolSpec, files: Sequence[str]) -> list[str]:
        """Build the shell-free argv for ``spec`` scoped to ``files``.

        For ``append_paths`` a trailing project-wide ``'.'`` is dropped and the
        sorted file paths are appended, so a project-wide command becomes
        file-scoped. ``whole_project`` and ``no_args`` run ``base_argv`` as-is.
        """
        base = list(spec.base_argv)
        if spec.scope_mode == "append_paths":
            if base and base[-1] == ".":
                base = base[:-1]
            return [*base, *sorted(files)]
        # whole_project / no_args: never append file paths.
        return base

    def _run_tool(self, spec: ToolSpec, files: Sequence[str]) -> ToolRun:
        """Run one tool as a subprocess (argv only — never ``shell=True``).

        Mirrors ``VerifyPhase._run_tests``: ``capture_output``, ``text``, a
        wall-clock ``timeout``, and ``cwd`` pinned to the project root. A
        timeout maps to ``exit_code == -1``; a missing executable to
        ``exit_code == -2`` with ``missing=True``.
        """
        argv = self._argv_for(spec, files)
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.root),
            )
        except subprocess.TimeoutExpired:
            return ToolRun(
                tool=spec.name,
                exit_code=_EXIT_TIMEOUT,
                stdout="",
                stderr=f"{spec.name} timed out after {self.timeout}s",
                missing=False,
            )
        except FileNotFoundError:
            return ToolRun(
                tool=spec.name,
                exit_code=_EXIT_MISSING,
                stdout="",
                stderr=f"{spec.name} not found",
                missing=True,
            )
        return ToolRun(
            tool=spec.name,
            exit_code=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            missing=False,
        )

    def _parse(self, spec: ToolSpec, run: ToolRun) -> list[Finding]:
        """Map a :class:`ToolRun` to findings via the spec's parser id."""
        parser = _PARSERS.get(spec.parser, _parse_exit_only)
        return parser(run, spec.severity)

    @staticmethod
    def _tool_missing_finding(spec: ToolSpec, files: Sequence[str]) -> Finding:
        """Build the ERROR finding for a missing *required* tool."""
        return Finding(
            rule="tool_missing",
            severity=CheckSeverity.ERROR,
            message=(
                f"Required tool '{spec.name}' is not installed; "
                f"install it to enforce this language's standards."
            ),
            file=files[0] if files else None,
            symbol=spec.name,
            category="language",
            metadata={"tool": spec.name},
        )


# --------------------------------------------------------------------------- #
# Parsers: parser id -> (ToolRun, severity) -> list[Finding]
# --------------------------------------------------------------------------- #


def _parse_exit_only(run: ToolRun, severity: CheckSeverity) -> list[Finding]:
    """A non-zero exit is a single project-scoped finding; zero is clean."""
    if run.exit_code == 0:
        return []
    detail = (run.stdout or run.stderr or "").strip()
    message = f"{run.tool} reported issues (exit {run.exit_code})"
    if detail:
        message = f"{message}: {detail.splitlines()[0][:200]}"
    return [
        Finding(
            rule=run.tool,
            severity=severity,
            message=message,
            category="language",
            metadata={"exit_code": run.exit_code},
        )
    ]


def _parse_ruff_json(run: ToolRun, severity: CheckSeverity) -> list[Finding]:
    """Parse ``ruff check --output-format json`` rows into findings."""
    rows = _safe_json(run.stdout)
    if rows is None:
        return _parse_exit_only(run, severity)
    findings: list[Finding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        location = row.get("location") or {}
        line = location.get("row") if isinstance(location, dict) else None
        code = str(row.get("code") or "")
        text = str(row.get("message") or "").strip()
        message = f"{code}: {text}" if code else text
        findings.append(
            Finding(
                rule="ruff",
                severity=severity,
                message=message or "ruff finding",
                file=_rel(row.get("filename")),
                line=_as_int(line),
                category="language",
                metadata={"code": code},
            )
        )
    return findings


def _parse_eslint_json(run: ToolRun, severity: CheckSeverity) -> list[Finding]:
    """Parse ``eslint --format json`` (list of file reports) into findings."""
    reports = _safe_json(run.stdout)
    if reports is None:
        return _parse_exit_only(run, severity)
    findings: list[Finding] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        file_path = _rel(report.get("filePath"))
        for msg in report.get("messages", []) or []:
            if not isinstance(msg, dict):
                continue
            rule_id = str(msg.get("ruleId") or "eslint")
            text = str(msg.get("message") or "").strip()
            # eslint severity 2 == error, 1 == warning.
            sev = CheckSeverity.ERROR if msg.get("severity") == 2 else severity
            findings.append(
                Finding(
                    rule="eslint",
                    severity=sev,
                    message=f"{rule_id}: {text}" if text else rule_id,
                    file=file_path,
                    line=_as_int(msg.get("line")),
                    category="language",
                    metadata={"rule_id": rule_id},
                )
            )
    return findings


def _parse_mypy_text(run: ToolRun, severity: CheckSeverity) -> list[Finding]:
    """Parse mypy's ``file:line: error: message`` text lines into findings."""
    if run.exit_code == 0:
        return []
    findings: list[Finding] = []
    for line in run.stdout.splitlines():
        parts = line.split(":", 3)
        # Expect at least file:line:severity: message
        if len(parts) < 4:
            continue
        file_part, line_part, sev_part, message = parts
        sev_token = sev_part.strip().lower()
        if sev_token not in ("error", "warning", "note"):
            continue
        if sev_token == "note":
            continue
        mapped = CheckSeverity.ERROR if sev_token == "error" else severity
        findings.append(
            Finding(
                rule="mypy",
                severity=mapped,
                message=message.strip() or "mypy finding",
                file=_rel(file_part),
                line=_as_int(line_part.strip()),
                category="language",
            )
        )
    if not findings:
        # Non-zero exit but no parseable lines: surface it rather than drop it.
        return _parse_exit_only(run, severity)
    return findings


def _parse_gofmt_list(run: ToolRun, severity: CheckSeverity) -> list[Finding]:
    """Parse ``gofmt -l`` output (one unformatted file path per line)."""
    findings: list[Finding] = []
    for raw in run.stdout.splitlines():
        path = raw.strip()
        if not path:
            continue
        findings.append(
            Finding(
                rule="gofmt",
                severity=severity,
                message="File is not gofmt-formatted",
                file=_rel(path),
                category="language",
            )
        )
    return findings


def _parse_bandit_json(run: ToolRun, severity: CheckSeverity) -> list[Finding]:
    """Parse ``bandit -f json`` results into findings."""
    payload = _safe_json(run.stdout)
    if not isinstance(payload, dict):
        return _parse_exit_only(run, severity) if run.exit_code != 0 else []
    findings: list[Finding] = []
    for issue in payload.get("results", []) or []:
        if not isinstance(issue, dict):
            continue
        test_id = str(issue.get("test_id") or "bandit")
        text = str(issue.get("issue_text") or "").strip()
        findings.append(
            Finding(
                rule="bandit",
                severity=severity,
                message=f"{test_id}: {text}" if text else test_id,
                file=_rel(issue.get("filename")),
                line=_as_int(issue.get("line_number")),
                category="language",
                metadata={"test_id": test_id},
            )
        )
    return findings


_PARSERS: dict[str, Callable[[ToolRun, CheckSeverity], list[Finding]]] = {
    "exit_only": _parse_exit_only,
    "ruff_json": _parse_ruff_json,
    "eslint_json": _parse_eslint_json,
    "mypy_text": _parse_mypy_text,
    "gofmt_list": _parse_gofmt_list,
    "bandit_json": _parse_bandit_json,
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #


def _safe_json(text: str) -> list[Any] | dict[str, Any] | None:
    """Parse JSON, returning ``None`` on any failure (degrade to exit_only)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(loaded, (list, dict)):
        return loaded
    return None


def _rel(value: object) -> str | None:
    """Normalize a tool-reported path to a project-relative POSIX string."""
    if not isinstance(value, str) or not value:
        return None
    return Path(value).as_posix()


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
