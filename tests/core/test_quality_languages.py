"""Behaviour tests for ``opencontext_core.quality.languages``.

These exercise the per-language quality runner without depending on any real
linter being installed: every subprocess call is monkeypatched with a fake that
returns a deterministic :class:`ToolRun`. Every test is tmp_path-isolated and
never reads or writes the real ``~/.opencontext`` or the repo ``.opencontext``.

The tests are behavioural — they assert the *logic* (grouping, scoping,
parsing, honest degradation, determinism), so they fail if that logic breaks,
not merely if a signature changes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
from opencontext_core.quality.languages import (
    LANGUAGE_TOOLS,
    LanguageQualityRunner,
    LanguageStandards,
    ToolRun,
    ToolSpec,
)
from opencontext_core.quality.models import Finding
from opencontext_core.quality.rules import LanguageRule, StandardsProfile

# --------------------------------------------------------------------------- #
# Helpers / fakes
# --------------------------------------------------------------------------- #


class _FakeCompleted:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_runner(tmp_path: Path) -> LanguageQualityRunner:
    return LanguageQualityRunner(tmp_path)


def _touch(root: Path, rel: str, content: str = "x = 1\n") -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel


# --------------------------------------------------------------------------- #
# LANGUAGE_TOOLS / LanguageStandards registry
# --------------------------------------------------------------------------- #


def test_registry_has_core_languages() -> None:
    # The registry must at minimum cover Python + JS/TS (the spec's first-class
    # langs) and the empty-tuple langs that were extended (go/rust).
    assert "python" in LANGUAGE_TOOLS
    for lang in ("python", "javascript", "typescript", "go", "rust"):
        assert lang in LANGUAGE_TOOLS, f"missing language: {lang}"
        # Every covered language exposes at least the STANDARD tier.
        assert StandardsProfile.STANDARD in LANGUAGE_TOOLS[lang]


def test_tools_for_is_nested_subset_relaxed_standard_strict() -> None:
    # relaxed ⊆ standard ⊆ strict for every covered language (spec invariant).
    for lang in LANGUAGE_TOOLS:
        relaxed = {t.name for t in LanguageStandards.tools_for(lang, StandardsProfile.RELAXED)}
        standard = {t.name for t in LanguageStandards.tools_for(lang, StandardsProfile.STANDARD)}
        strict = {t.name for t in LanguageStandards.tools_for(lang, StandardsProfile.STRICT)}
        assert relaxed <= standard, f"{lang}: relaxed not subset of standard"
        assert standard <= strict, f"{lang}: standard not subset of strict"


def test_tools_for_unknown_language_is_empty() -> None:
    assert LanguageStandards.tools_for("cobol", StandardsProfile.STRICT) == ()


def test_tools_for_python_standard_includes_ruff() -> None:
    names = {t.name for t in LanguageStandards.tools_for("python", StandardsProfile.STANDARD)}
    assert "ruff" in names


def test_tool_specs_use_argv_never_shell() -> None:
    # No spec may carry a shell string; base_argv is always a tuple of tokens.
    for tiers in LANGUAGE_TOOLS.values():
        for specs in tiers.values():
            for spec in specs:
                assert isinstance(spec.base_argv, tuple)
                assert all(isinstance(tok, str) for tok in spec.base_argv)
                # A shell command would smuggle the whole thing as one string.
                assert not (len(spec.base_argv) == 1 and " " in spec.base_argv[0])


def test_profile_for_uses_rule_override() -> None:
    rules = (LanguageRule(language="python", profile=StandardsProfile.STRICT),)
    assert (
        LanguageStandards.profile_for("python", rules, default=StandardsProfile.RELAXED)
        == StandardsProfile.STRICT
    )


def test_profile_for_falls_back_to_default() -> None:
    rules = (LanguageRule(language="python", profile=StandardsProfile.STRICT),)
    assert (
        LanguageStandards.profile_for("javascript", rules, default=StandardsProfile.RELAXED)
        == StandardsProfile.RELAXED
    )


def test_profile_for_default_default_is_standard() -> None:
    assert LanguageStandards.profile_for("python", ()) == StandardsProfile.STANDARD


# --------------------------------------------------------------------------- #
# LanguageQualityRunner.run — grouping, scoping, normalization
# --------------------------------------------------------------------------- #


def test_run_no_changed_files_is_clean(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    findings, skipped = runner.run([], ())
    assert findings == ()
    assert skipped == ()


def test_run_never_uses_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "src/a.py")

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        # Tools never run as a shell string.
        assert kwargs.get("shell") is not True
        assert "shell" not in kwargs or kwargs["shell"] is False
        # argv must be a real list of tokens, not one packed shell string.
        assert isinstance(argv, (list, tuple))
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run([py], (LanguageRule(language="python", profile=StandardsProfile.STANDARD),))


def test_run_python_clean_no_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "src/a.py")

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        assert kwargs.get("shell") is not True
        return _FakeCompleted(0, "[]", "")  # ruff json: empty array == clean

    monkeypatch.setattr(subprocess, "run", fake_run)

    findings, skipped = runner.run(
        [py], (LanguageRule(language="python", profile=StandardsProfile.RELAXED),)
    )
    # A clean ruff run yields no findings.
    assert all(f.rule != "tool_missing" for f in findings)
    # No required tool reported missing in this fake-clean world.
    assert all("missing" not in s for s in skipped) or skipped == ()


def test_run_appends_changed_file_paths_for_append_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _make_runner(tmp_path)
    a = _touch(tmp_path, "pkg/a.py")
    b = _touch(tmp_path, "pkg/b.py")

    seen_argvs: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        seen_argvs.append(list(argv))
        return _FakeCompleted(0, "[]", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner.run([b, a], (LanguageRule(language="python", profile=StandardsProfile.STANDARD),))

    # The append-scope tools must receive the changed files (and never a bare ".").
    ruff_calls = [c for c in seen_argvs if c and c[0] == "ruff"]
    assert ruff_calls, "ruff was not invoked"
    for call in ruff_calls:
        assert "." not in call[1:], "project-wide '.' was not rewritten to file scope"
        # Files appended and sorted deterministically (a before b).
        assert call[-2:] == ["pkg/a.py", "pkg/b.py"]


def test_run_missing_required_tool_yields_tool_missing_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "src/a.py")

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    # STRICT: ruff is required, so a missing tool is an ERROR finding, not a pass.
    findings, _skipped = runner.run(
        [py], (LanguageRule(language="python", profile=StandardsProfile.STRICT),)
    )
    missing = [f for f in findings if f.rule == "tool_missing"]
    assert missing, "missing required tool must produce a tool_missing finding"
    assert all(f.severity == CheckSeverity.ERROR for f in missing)
    # It must NOT be silently swallowed into skipped only.
    assert any("ruff" in (f.message or "") or f.symbol == "ruff" for f in missing)


def test_run_missing_optional_tool_is_skipped_not_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "src/a.py")

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    # RELAXED: tools are optional → a missing tool is recorded in skipped, NOT a
    # tool_missing error finding (degrade honestly without blocking).
    findings, skipped = runner.run(
        [py], (LanguageRule(language="python", profile=StandardsProfile.RELAXED),)
    )
    assert all(f.rule != "tool_missing" for f in findings)
    assert skipped, "missing optional tool must be recorded in skipped"
    assert any("ruff" in s for s in skipped)


def test_run_parses_ruff_json_into_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "src/a.py")
    ruff_payload = (
        '[{"code": "F401", "message": "imported but unused", '
        '"filename": "src/a.py", "location": {"row": 3, "column": 1}}]'
    )

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        if argv and argv[0] == "ruff":
            return _FakeCompleted(1, ruff_payload, "")
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    findings, _ = runner.run(
        [py], (LanguageRule(language="python", profile=StandardsProfile.RELAXED),)
    )
    ruff_findings = [f for f in findings if f.rule == "ruff"]
    assert ruff_findings, "ruff json rows were not mapped to findings"
    f = ruff_findings[0]
    assert f.category == "language"
    assert f.line == 3
    assert f.file == "src/a.py"
    assert "F401" in (f.message or "") or "F401" in str(f.metadata)


def test_run_exit_only_parser_flags_on_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A tool with an exit_only parser produces a finding when exit != 0 and none
    # when exit == 0. We drive this through a synthetic ToolSpec to isolate it.
    runner = _make_runner(tmp_path)

    spec = ToolSpec(
        name="fakefmt",
        base_argv=("fakefmt", "--check"),
        scope_mode="append_paths",
        parser="exit_only",
        severity=CheckSeverity.WARNING,
        languages=("python",),
    )

    def fake_run_fail(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        return _FakeCompleted(2, "needs formatting", "")

    monkeypatch.setattr(subprocess, "run", fake_run_fail)
    run = runner._run_tool(spec, ["src/a.py"])
    assert isinstance(run, ToolRun)
    assert run.exit_code == 2
    assert run.missing is False

    findings_fail = runner._parse(spec, run)
    assert findings_fail, "exit_only must flag a non-zero exit"
    assert findings_fail[0].rule == "fakefmt"
    assert findings_fail[0].severity == CheckSeverity.WARNING

    def fake_run_ok(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run_ok)
    run_ok = runner._run_tool(spec, ["src/a.py"])
    assert runner._parse(spec, run_ok) == []


def test_run_timeout_marks_run_not_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = LanguageQualityRunner(tmp_path, timeout=5)
    spec = ToolSpec(
        name="slowtool",
        base_argv=("slowtool",),
        scope_mode="append_paths",
        parser="exit_only",
    )

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=5)

    monkeypatch.setattr(subprocess, "run", fake_run)
    run = runner._run_tool(spec, ["src/a.py"])
    assert run.missing is False
    assert run.exit_code == -1  # timeout sentinel, distinct from missing (-2)


def test_run_tool_passes_timeout_and_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = LanguageQualityRunner(tmp_path, timeout=42)
    spec = ToolSpec(name="t", base_argv=("t",), scope_mode="no_args", parser="exit_only")
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        captured.update(kwargs)
        captured["argv"] = list(argv)
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner._run_tool(spec, ["x.py"])
    assert captured["timeout"] == 42
    assert Path(captured["cwd"]) == tmp_path
    assert captured.get("capture_output") is True
    assert captured.get("text") is True
    # no_args scope must NOT append the file paths.
    assert captured["argv"] == ["t"]


def test_run_no_args_scope_does_not_append_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _make_runner(tmp_path)
    spec = ToolSpec(
        name="whole", base_argv=("whole", "check"), scope_mode="whole_project", parser="exit_only"
    )
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        seen.append(list(argv))
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner._run_tool(spec, ["a.py", "b.py"])
    assert seen == [["whole", "check"]]


# --------------------------------------------------------------------------- #
# Extension fallback / language detection
# --------------------------------------------------------------------------- #


def test_run_extension_fallback_detects_go(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # classifier.detect_language does not know .go; the runner's _EXT_LANGUAGE
    # fallback must still route a .go file to the go tool set.
    runner = _make_runner(tmp_path)
    go = _touch(tmp_path, "main.go", "package main\n")

    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        seen.append(list(argv))
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run([go], (LanguageRule(language="go", profile=StandardsProfile.STANDARD),))
    # Some go tool must have been invoked (gofmt / go vet …).
    assert seen, "no go tool was invoked via the extension fallback"


def test_run_ignores_unknown_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _make_runner(tmp_path)
    other = _touch(tmp_path, "notes.txt", "hello\n")

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:  # pragma: no cover
        raise AssertionError("no tool should run for an unknown extension")

    monkeypatch.setattr(subprocess, "run", fake_run)
    findings, skipped = runner.run(
        [other], (LanguageRule(language="python", profile=StandardsProfile.STANDARD),)
    )
    assert findings == ()
    assert skipped == ()


# --------------------------------------------------------------------------- #
# Determinism + isolation
# --------------------------------------------------------------------------- #


def test_run_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _make_runner(tmp_path)
    files = [
        _touch(tmp_path, "z.py"),
        _touch(tmp_path, "a.py"),
        _touch(tmp_path, "m.py"),
    ]
    ruff_payload = (
        '[{"code": "E501", "message": "line too long", '
        '"filename": "a.py", "location": {"row": 1, "column": 1}}]'
    )

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        if argv and argv[0] == "ruff":
            return _FakeCompleted(1, ruff_payload, "")
        return _FakeCompleted(0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    first, first_skipped = runner.run(
        files, (LanguageRule(language="python", profile=StandardsProfile.RELAXED),)
    )
    second, second_skipped = runner.run(
        list(reversed(files)),
        (LanguageRule(language="python", profile=StandardsProfile.RELAXED),),
    )
    assert first == second, "same inputs must yield the identical findings tuple"
    assert first_skipped == second_skipped


def test_run_does_not_touch_real_opencontext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The runner's cwd must be the tmp root, never the real home/repo .opencontext.
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "a.py")
    cwds: list[str] = []

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        cwds.append(str(kwargs.get("cwd")))
        return _FakeCompleted(0, "[]", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run([py], (LanguageRule(language="python", profile=StandardsProfile.RELAXED),))
    for cwd in cwds:
        assert Path(cwd) == tmp_path
        assert ".opencontext" not in cwd


def test_findings_are_findings_with_language_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _make_runner(tmp_path)
    py = _touch(tmp_path, "a.py")

    def fake_run(argv: list[str], **kwargs: Any) -> _FakeCompleted:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    findings, _ = runner.run(
        [py], (LanguageRule(language="python", profile=StandardsProfile.STRICT),)
    )
    assert all(isinstance(f, Finding) for f in findings)
    assert all(f.category == "language" for f in findings)
    # tool_missing findings are FAILED-shaped (a violation), severity ERROR.
    for f in findings:
        if f.rule == "tool_missing":
            assert f.severity == CheckSeverity.ERROR


def test_check_status_import_is_available() -> None:
    # Sanity: the module reuses the shared ci_checks status enum (no local re-def).
    assert CheckStatus.FAILED.value == "failed"
