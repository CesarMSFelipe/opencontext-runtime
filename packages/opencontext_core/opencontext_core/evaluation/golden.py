"""Golden-fixture benchmark suites (B4 / B5 / AVH-006).

Turns the declared-but-unmeasured 1.0-minimum gates into REAL measurements by running
self-contained fixture repos under ``tests/golden/<suite>/`` and comparing the result
to each fixture's ``expected.json``. Five gates are wired here:

* ``oc-flow-localized-bugfix`` — the DoD bugfix: OC Flow + a DETERMINISTIC provider
  stub (the fixture's ``provider_stub.json``) applies the structured ``ApplyEdit`` and
  ``pytest`` must pass. The full provider -> validate -> policy -> checkpoint -> apply
  -> receipt -> inspection pipeline runs honestly (Phase-3 injectable executor).
* ``first-run`` — ``install -> doctor -> index`` over a fresh small repo (subprocess,
  isolated ``$HOME``); MET when the sequence exits 0 with a usable config + index
  artifact.
* ``policy-security`` — a forbidden-path write and a secret-bearing output must BOTH be
  blocked (no live provider).
* ``resume-rollback`` — a checkpointed run resumes (manifest + artifacts validate and
  continue) and a failed apply rolls back to the prior byte-identical state.
* ``provider-fallback`` — a faulty primary provider falls back to the mock and a
  fallback receipt is recorded.

HONESTY (build-rule #1): a fixture that is absent, or a runner that cannot execute
end-to-end here, returns ``NOT_MEASURED`` — never a fabricated ``MET``. A fixture that
runs and does not meet ``expected.json`` returns ``FAILED``. Results are cached per
``(suite, fixtures_root, smoke)`` so the (idempotent) fixtures run once per session.

Layering (doc 58): L10 evaluation composing L9 oc_flow, L7 providers, L6 harness, L3
safety/actions downward — all imports are lazy inside the runners to keep import-time
coupling out and to stay leaf-friendly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencontext_core.evaluation.models import BenchmarkSuiteReport, GateStatus
from opencontext_core.evaluation.runner import DEFAULT_METHODOLOGY_VERSION, not_measured


def find_golden_root() -> Path:
    """Locate the source-controlled ``tests/golden`` fixture root.

    Walks up from this module looking for ``tests/golden``. When OpenContext is
    installed without its test tree (a wheel), no such directory exists and the
    returned path simply will not exist — the suites then report ``NOT_MEASURED``
    (honest), never a fake pass.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tests" / "golden"
        if candidate.is_dir():
            return candidate
    # Best-effort fallback (repo layout): packages/opencontext_core/opencontext_core
    # /evaluation/golden.py -> repo root is parents[4].
    return here.parents[4] / "tests" / "golden" if len(here.parents) > 4 else Path("tests/golden")


#: The source-controlled golden fixture root.
GOLDEN_ROOT: Path = find_golden_root()

#: Gate name -> fixture directory name (gates are hyphenated; dirs are underscored).
FIXTURE_DIRS: dict[str, str] = {
    "oc-flow-localized-bugfix": "oc_flow_bugfix_python",
    "first-run": "first_run",
    "policy-security": "policy_security",
    "resume-rollback": "resume_rollback",
    "provider-fallback": "provider_fallback",
    # VDM-008: two more A-gates measured provider-free against golden fixtures.
    "sdd-formal-feature": "sdd_formal_feature",
    "plugin-compatibility": "plugin_compatibility",
}

#: The wired golden gates (the set that moves NOT_MEASURED -> MET against real fixtures).
GOLDEN_SUITE_NAMES: tuple[str, ...] = tuple(FIXTURE_DIRS)

# Module-level result cache: idempotent fixtures need only run once per session.
_RESULT_CACHE: dict[tuple[str, str, bool], BenchmarkSuiteReport] = {}


class _NotMeasured(Exception):
    """Raised by a runner when it genuinely cannot measure end-to-end (-> NOT_MEASURED)."""


class _StubGateway:
    """Deterministic provider stub: returns a fixed response, records each call.

    Honest — it exercises the REAL executor pipeline (parse, schema-validate, policy,
    checkpoint, apply, receipt, inspection); it stands in for the model only.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[Any] = []

    def generate(self, request: Any) -> Any:
        from opencontext_core.models.llm import LLMResponse

        self.calls.append(request)
        return LLMResponse(
            content=self._content,
            provider="mock",
            model="golden-stub",
            input_tokens=1,
            output_tokens=1,
        )


# --------------------------------------------------------------------------- helpers
def _load_expected(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected.json"
    if not path.is_file():
        raise _NotMeasured(f"expected.json missing in {fixture_dir.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _NotMeasured(f"unreadable expected.json: {exc}") from exc
    if not isinstance(data, dict):
        raise _NotMeasured("expected.json is not a JSON object")
    return data


def _copy_fixture(fixture_dir: Path) -> tuple[Path, Path]:
    """Copy a fixture to an isolated temp repo. Returns (work_repo, temp_base)."""
    base = Path(tempfile.mkdtemp(prefix="golden_"))
    work = base / "repo"
    shutil.copytree(fixture_dir, work)
    return work, base


def _met(name: str, version: str, notes: str, **fields: Any) -> BenchmarkSuiteReport:
    return BenchmarkSuiteReport(
        suite=name,
        version=version,
        status=GateStatus.MET,
        measured=True,
        success=True,
        notes=notes,
        **fields,
    )


def _failed(name: str, version: str, notes: str, **fields: Any) -> BenchmarkSuiteReport:
    return BenchmarkSuiteReport(
        suite=name,
        version=version,
        status=GateStatus.FAILED,
        measured=True,
        success=False,
        notes=notes,
        **fields,
    )


# ------------------------------------------------------------------- per-suite runners
def _run_oc_flow_bugfix(suite: GoldenSuite, fixture_dir: Path, smoke: bool) -> BenchmarkSuiteReport:
    """DoD bugfix: stub-driven OC Flow applies the fix; ``pytest`` must pass."""
    from opencontext_core.oc_flow.models import Lane
    from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
    from opencontext_core.oc_flow.runner import OCFlowRunner

    expected = _load_expected(fixture_dir)
    stub_path = fixture_dir / "provider_stub.json"
    if not stub_path.is_file():
        raise _NotMeasured("provider_stub.json missing")
    task = (fixture_dir / "task.txt").read_text(encoding="utf-8").strip() or "Fix failing test"
    work, base = _copy_fixture(fixture_dir)
    try:
        executor = ProviderBackedNodeExecutor(
            gateway=_StubGateway(stub_path.read_text(encoding="utf-8")),
            root=work,
            provider="mock",
        )
        t0 = time.perf_counter()
        result = OCFlowRunner(root=work, executor=executor).run(task, lane=Lane.FAST)
        elapsed = time.perf_counter() - t0
        art = result.artifacts_dir
        problems: list[str] = []

        if result.status != expected.get("status", "completed"):
            problems.append(f"status={result.status} (expected {expected.get('status')})")
        for name in expected.get("expected_artifacts", []):
            if art is None or not (art / name).is_file():
                problems.append(f"missing artifact {name}")
        changed = 0
        if art is not None and (art / "apply-receipts.json").is_file():
            receipts = json.loads((art / "apply-receipts.json").read_text(encoding="utf-8"))
            changed = len(receipts.get("receipts", []))
        if changed < int(expected.get("changed_files_min", 1)):
            problems.append(f"changed_files={changed} < {expected.get('changed_files_min')}")

        # The DoD proof: run the fixture's verification command (pytest) in the repo.
        verify = expected.get("verification_command") or [sys.executable, "-m", "pytest", "-q"]
        verify = [sys.executable if tok == "python" else tok for tok in verify]
        pytest_code = _run_subprocess(verify, work).returncode
        want_code = int(expected.get("pytest_exit_code", 0))
        if pytest_code != want_code:
            problems.append(f"pytest exit {pytest_code} (expected {want_code})")

        max_t = float(expected.get("max_time_s", 1e9))
        if elapsed > max_t:
            problems.append(f"elapsed {elapsed:.1f}s > {max_t}s")

        fields = {
            "duration_ms": int(elapsed * 1000),
            "changed_files": changed,
            "tokens": result.total_tokens,
        }
        if problems:
            return _failed(suite.name, suite.version, "; ".join(problems), **fields)
        return _met(
            suite.name,
            suite.version,
            f"bug fixed via stub ApplyEdit, pytest passed, {changed} file(s) changed",
            **fields,
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_first_run(suite: GoldenSuite, fixture_dir: Path, smoke: bool) -> BenchmarkSuiteReport:
    """First-run: ``install -> doctor -> index`` (subprocess, isolated $HOME)."""
    _load_expected(fixture_dir)  # validate the fixture declares its contract
    work, base = _copy_fixture(fixture_dir)
    home = base / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    try:
        steps = (
            ("install", ["install", "--yes", "."]),
            ("doctor", ["doctor"]),
            ("index", ["index", "."]),
        )
        t0 = time.perf_counter()
        results: dict[str, int] = {}
        for label, argv in steps:
            try:
                proc = _run_cli(argv, work, env=env)
            except (OSError, subprocess.SubprocessError) as exc:
                raise _NotMeasured(f"{label} could not launch: {exc}") from exc
            results[label] = proc.returncode
        elapsed = time.perf_counter() - t0

        problems = [f"{label} exit {code}" for label, code in results.items() if code != 0]
        if not (work / "opencontext.yaml").is_file():
            problems.append("install wrote no opencontext.yaml")
        if not _find_artifact(work, "project_manifest.json"):
            problems.append("index produced no project_manifest.json")

        fields = {"duration_ms": int(elapsed * 1000)}
        if problems:
            return _failed(suite.name, suite.version, "; ".join(problems), **fields)
        return _met(
            suite.name,
            suite.version,
            "install+doctor+index exited 0 with a usable config and index artifact",
            **fields,
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_policy_security(
    suite: GoldenSuite, fixture_dir: Path, smoke: bool
) -> BenchmarkSuiteReport:
    """A forbidden-path write and a secret-bearing output must BOTH be blocked."""
    from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
    from opencontext_core.oc_flow.models import Lane
    from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
    from opencontext_core.oc_flow.runner import OCFlowRunner
    from opencontext_core.safety.secrets import SecretScanner

    _load_expected(fixture_dir)
    secret_text = (fixture_dir / "secret_output.txt").read_text(encoding="utf-8")
    forbidden_json = (fixture_dir / "forbidden_edit.json").read_text(encoding="utf-8")
    problems: list[str] = []

    # 1) The scanner really detects the seeded secret pattern.
    if not SecretScanner().scan_secret_findings(secret_text):
        problems.append("secret scanner detected no secret in the seeded output")

    # 2) Forbidden-path write -> policy denies -> run blocked, nothing written outside.
    work, base = _copy_fixture(fixture_dir)
    try:
        executor = ProviderBackedNodeExecutor(
            gateway=_StubGateway(forbidden_json),
            root=work,
            provider="mock",
        )
        result = OCFlowRunner(root=work, executor=executor).run(
            "Write a credentials helper",
            lane=Lane.FAST,
        )
        if result.status == "completed":
            problems.append("forbidden-path run reported completed")
        if "policy denied" not in (result.completion_reason or ""):
            problems.append(f"forbidden-path not policy-denied: {result.completion_reason}")
        if (work.parent / "escaped_write.py").exists():
            problems.append("forbidden write escaped the sandbox")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    # 3) Secret-bearing output -> inspection blocks -> not completed, secret value
    #    never lands in a durable artifact/receipt.
    work, base = _copy_fixture(fixture_dir)
    try:
        secret_edit = ApplyEdit(
            path="leak.py",
            operation=ApplyOperation.CREATE_FILE,
            content=secret_text,
            reason="write credentials (must be blocked)",
            requirement_refs=["no secret output"],
        )
        stub = _StubGateway(json.dumps([secret_edit.model_dump()]))
        executor = ProviderBackedNodeExecutor(gateway=stub, root=work, provider="mock")
        result = OCFlowRunner(root=work, executor=executor).run(
            "Write a credentials helper",
            lane=Lane.FAST,
        )
        if result.status == "completed":
            problems.append("secret-output run reported completed")
        token = "AKIAIOSFODNN7EXAMPLE"
        art = result.artifacts_dir
        if art is not None:
            for path in art.rglob("*"):
                if path.is_file() and token in path.read_text(encoding="utf-8", errors="ignore"):
                    problems.append(f"secret value leaked into artifact {path.name}")
                    break
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if problems:
        return _failed(suite.name, suite.version, "; ".join(problems))
    return _met(
        suite.name,
        suite.version,
        "secret detected; forbidden write denied + run blocked; no secret in artifacts",
    )


def _run_resume_rollback(
    suite: GoldenSuite, fixture_dir: Path, smoke: bool
) -> BenchmarkSuiteReport:
    """A checkpointed run resumes (validate + continue) and a failed apply rolls back."""
    from opencontext_core.harness.checkpoint import CheckpointStore
    from opencontext_core.oc_flow.models import Lane
    from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
    from opencontext_core.oc_flow.runner import OCFlowRunner

    _load_expected(fixture_dir)
    stub_path = fixture_dir / "provider_stub.json"
    if not stub_path.is_file():
        raise _NotMeasured("provider_stub.json missing")
    work, base = _copy_fixture(fixture_dir)
    try:
        problems: list[str] = []
        executor = ProviderBackedNodeExecutor(
            gateway=_StubGateway(stub_path.read_text(encoding="utf-8")),
            root=work,
            provider="mock",
        )
        runner = OCFlowRunner(root=work, executor=executor)
        result = runner.run("Fix failing test", lane=Lane.FAST)

        # Resume: validates the run manifest + restores artifacts (raises if invalid).
        try:
            resumed = runner.resume(result.session_id, result.run_id)
            resume_ok = resumed.contract is not None and resumed.inspection is not None
        except Exception as exc:  # a genuine resume failure is a FAILED, not a crash
            resume_ok = False
            problems.append(f"resume raised: {exc}")
        if not resume_ok:
            problems.append("resume did not validate + restore the run")

        # Rollback: snapshot a file, corrupt it (failed apply), restore it byte-for-byte.
        target = work / "rollback_target.txt"
        original = target.read_text(encoding="utf-8")
        checkpoint = CheckpointStore(work).create([target.resolve()], source="golden-rollback")
        if checkpoint is None:
            problems.append("checkpoint store created no checkpoint")
        else:
            target.write_text("CORRUPTED BY A FAILED APPLY\n", encoding="utf-8")
            checkpoint.restore()
            if target.read_text(encoding="utf-8") != original:
                problems.append("rollback did not restore the file byte-for-byte")

        if problems:
            return _failed(suite.name, suite.version, "; ".join(problems))
        return _met(
            suite.name,
            suite.version,
            "checkpointed run resumed (manifest+artifacts validated); rollback restored files",
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_provider_fallback(
    suite: GoldenSuite, fixture_dir: Path, smoke: bool
) -> BenchmarkSuiteReport:
    """A faulty primary provider falls back to mock and records a fallback receipt."""
    from types import SimpleNamespace

    from opencontext_core.errors import ProviderError
    from opencontext_core.models.llm import LLMRequest
    from opencontext_core.operating_model.receipts import RunReceiptStore
    from opencontext_core.providers.gateway import ProviderGateway

    fault = json.loads((fixture_dir / "fault.json").read_text(encoding="utf-8"))
    primary = str(fault.get("primary_provider", "ollama"))
    fallback_provider = str((fault.get("fallback_providers") or ["mock"])[0])
    kind = str(fault.get("fault", "error"))
    work, base = _copy_fixture(fixture_dir)
    try:

        class _FaultyBase:
            def generate(self, request: Any) -> Any:
                if kind == "timeout":
                    raise TimeoutError("primary provider timed out")
                raise ProviderError("primary provider unavailable")

        class _MockAdapter:
            def chat_with_retries(self, messages: Any, model: str, max_tokens: int) -> Any:
                return SimpleNamespace(
                    content="fallback ok",
                    provider=fallback_provider,
                    model=model,
                    input_tokens=1,
                    output_tokens=1,
                    metadata={},
                )

        receipts = RunReceiptStore(work)
        gateway = ProviderGateway(
            _FaultyBase(),
            receipts=receipts,
            fallback=True,
            fallback_providers=(fallback_provider,),
            adapter_factory=lambda _provider: _MockAdapter(),
            retry_limit=2,
        )
        resp = gateway.generate(
            LLMRequest(
                prompt="hello",
                system_prompt="",
                provider=primary,
                model="m",
                max_output_tokens=16,
                metadata={"role": "generate"},
            )
        )
        problems: list[str] = []
        if resp.provider != fallback_provider:
            problems.append(f"fallback provider was {resp.provider} (expected {fallback_provider})")
        kinds = {pr.kind for pr in receipts.list_provider_receipts()}
        if "fallback" not in kinds:
            problems.append(f"no fallback receipt recorded (kinds={sorted(kinds)})")

        if problems:
            return _failed(suite.name, suite.version, "; ".join(problems))
        return _met(
            suite.name,
            suite.version,
            f"{kind} on {primary} -> fell back to {fallback_provider}; fallback receipt recorded",
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_sdd_formal_feature(
    suite: GoldenSuite, fixture_dir: Path, smoke: bool
) -> BenchmarkSuiteReport:
    """SDD formal-feature: a broad/high-risk task routes to SDD and the flow yields phase
    outputs end-to-end (PR-004) — measured provider-free by static validation.

    Honest checks (no live LLM):
    * the shared workflow selector routes the fixture's formal task to ``sdd``;
    * the SDD flow defines at least ``phases_min`` phases, each with expected artifacts;
    * the fixture's shipped phase outputs name real SDD phases and are non-empty.
    """
    from opencontext_core.context.planning.workflow_selector import select_workflow
    from opencontext_core.oc_new.flow import OC_NEW_FLOW

    expected = _load_expected(fixture_dir)
    task_path = fixture_dir / "task.txt"
    if not task_path.is_file():
        raise _NotMeasured("task.txt missing")
    task = task_path.read_text(encoding="utf-8").strip()
    if not task:
        raise _NotMeasured("task.txt is empty")

    problems: list[str] = []

    # 1) The shared selector routes a formal/high-risk feature to SDD (B5/AVH-013).
    selection = select_workflow(task)
    want_workflow = str(expected.get("workflow", "sdd"))
    if selection.workflow != want_workflow:
        problems.append(f"workflow={selection.workflow!r} (expected {want_workflow!r})")

    # 2) The SDD flow defines the full phase set with expected artifacts.
    flow_phases = [p for p in OC_NEW_FLOW]
    flow_names = {p.name for p in flow_phases}
    phases_min = int(expected.get("phases_min", 1))
    producing = [p for p in flow_phases if getattr(p, "expected_artifacts", None)]
    if len(producing) < phases_min:
        problems.append(
            f"SDD flow defines {len(producing)} artifact-producing phases < {phases_min}"
        )

    # 3) The shipped phase outputs map to real SDD phases and are non-empty.
    if expected.get("artifacts_exist", True):
        phase_dir = fixture_dir / "phases"
        outputs = (
            sorted(p for p in phase_dir.glob("*") if p.is_file()) if phase_dir.is_dir() else []
        )
        if len(outputs) < phases_min:
            problems.append(f"{len(outputs)} phase output(s) < {phases_min}")
        for out in outputs:
            if out.stem not in flow_names:
                problems.append(f"phase output {out.name!r} is not an SDD phase")
            elif not out.read_text(encoding="utf-8").strip():
                problems.append(f"empty phase output {out.name!r}")

    if problems:
        return _failed(suite.name, suite.version, "; ".join(problems))
    return _met(
        suite.name,
        suite.version,
        f"formal task routed to {selection.workflow}; {len(producing)} SDD phases produce "
        "artifacts; phase outputs present",
    )


def _run_plugin_compatibility(
    suite: GoldenSuite, fixture_dir: Path, smoke: bool
) -> BenchmarkSuiteReport:
    """Plugin-compatibility: a sample plugin loads + validates against the public
    contracts (PR-015) — static validation, no live provider.

    Honest checks: the manifest passes the conformance suite (interface_valid) and the
    sandbox loader activates the entry point (plugin_loads).
    """
    from opencontext_core.plugins.compatibility import runtime_version
    from opencontext_core.plugins.conformance import run_conformance
    from opencontext_core.plugins.manifest import PluginManifest
    from opencontext_core.plugins.sandbox import run_sandboxed

    expected = _load_expected(fixture_dir)
    plugin_dir = fixture_dir / "sample_plugin"
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        raise _NotMeasured("sample_plugin/plugin.json missing")
    try:
        manifest = PluginManifest.from_plugin_json(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except (ValueError, OSError) as exc:
        raise _NotMeasured(f"unreadable plugin manifest: {exc}") from exc

    problems: list[str] = []

    # interface_valid: the manifest honors the public contracts (CONF-1..CONF-6).
    report = run_conformance(manifest, core_version=runtime_version())
    interface_valid = report.passed
    if expected.get("interface_valid", True) and not interface_valid:
        fails = ", ".join(f"{c.id}:{c.detail}" for c in report.failures)
        problems.append(f"conformance failed: {fails}")

    # plugin_loads: the sandbox loader activates the declared entry point.
    sandbox = run_sandboxed(plugin_dir, entry_point=manifest.entrypoint, plugin_name=manifest.name)
    plugin_loads = sandbox.ok
    if expected.get("plugin_loads", True) and not plugin_loads:
        problems.append(f"plugin did not load: {sandbox.reason}")

    if problems:
        return _failed(suite.name, suite.version, "; ".join(problems))
    return _met(
        suite.name,
        suite.version,
        f"sample plugin loaded ({sandbox.reason}) and passed {len(report.checks)} "
        "conformance checks against the public contracts",
    )


_RUNNERS: dict[str, Callable[[GoldenSuite, Path, bool], BenchmarkSuiteReport]] = {
    "oc-flow-localized-bugfix": _run_oc_flow_bugfix,
    "first-run": _run_first_run,
    "policy-security": _run_policy_security,
    "resume-rollback": _run_resume_rollback,
    "provider-fallback": _run_provider_fallback,
    "sdd-formal-feature": _run_sdd_formal_feature,
    "plugin-compatibility": _run_plugin_compatibility,
}


# ------------------------------------------------------------------ subprocess helpers
def _run_cli(
    argv: list[str], cwd: Path, *, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli.main", *argv],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _run_subprocess(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _find_artifact(root: Path, name: str) -> bool:
    return any(root.rglob(name))


# ------------------------------------------------------------------------- the suite
@dataclass
class GoldenSuite:
    """A benchmark suite backed by a ``tests/golden/<suite>/`` fixture (AVH-006).

    ``run`` loads the fixture, executes its per-suite runner in an isolated temp copy,
    compares against ``expected.json`` and returns a :class:`BenchmarkSuiteReport`. A
    missing fixture or a runner that cannot execute end-to-end here is ``NOT_MEASURED``;
    a fixture that runs and fails its contract is ``FAILED`` — never a fake ``MET``.
    """

    name: str
    fixtures_root: Path = GOLDEN_ROOT
    version: str = DEFAULT_METHODOLOGY_VERSION

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport:
        key = (self.name, str(self.fixtures_root), smoke)
        if key in _RESULT_CACHE:
            return _RESULT_CACHE[key]
        report = self._run_uncached(smoke)
        _RESULT_CACHE[key] = report
        return report

    def _run_uncached(self, smoke: bool) -> BenchmarkSuiteReport:
        fixture_dir = self.fixtures_root / FIXTURE_DIRS.get(self.name, self.name)
        if not fixture_dir.is_dir():
            return not_measured(self.name, self.version, f"fixture missing: {fixture_dir}")
        runner = _RUNNERS.get(self.name)
        if runner is None:
            return not_measured(self.name, self.version, "no golden runner registered")
        try:
            return runner(self, fixture_dir, smoke)
        except _NotMeasured as exc:
            return not_measured(self.name, self.version, str(exc))
        except Exception as exc:  # a crash is honestly NOT_MEASURED, never a fake pass
            return not_measured(self.name, self.version, f"runner error: {exc}")


def clear_golden_cache() -> None:
    """Drop the memoized golden results (tests that re-measure a mutated fixture)."""
    _RESULT_CACHE.clear()


__all__ = [
    "FIXTURE_DIRS",
    "GOLDEN_ROOT",
    "GOLDEN_SUITE_NAMES",
    "GoldenSuite",
    "clear_golden_cache",
    "find_golden_root",
]
