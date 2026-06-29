# Golden fixtures (B4 / B5 / AVH-006)

Real, self-contained fixture repos that make the release-acceptance benchmark gates
actually MEASURE (`MET` / `FAILED`) instead of `NOT_MEASURED`. All five are
**provider-free**: they need no live LLM. The two mutation suites drive OC Flow
through the Phase-3 injectable `ProviderBackedNodeExecutor` with a **deterministic
provider stub** (the fixture's `provider_stub.json`), so the full
provider → validate → policy → checkpoint → apply → receipt → inspection pipeline
runs honestly.

## Layout

Each `tests/golden/<suite>/` carries:

| File | Purpose |
|------|---------|
| setup files | the buggy/target repo state |
| `task.txt` | the task string |
| `provider_stub.json` | (mutation suites) the known-correct `ApplyEdit` set the stub returns |
| `expected.json` | expected workflow, artifacts, verification command, result, max tokens/time/mutation |

## 1.0-minimum wired suites (move NOT_MEASURED → MET/FAILED)

| Fixture dir | Gate | What it proves |
|-------------|------|----------------|
| `oc_flow_bugfix_python/` | `oc-flow-localized-bugfix` | the DoD bugfix: buggy `add()` + failing test → OC Flow applies the fix → `pytest` passes |
| `first_run/` | `first-run` | `install → doctor --strict → index` complete with a usable config + index artifact |
| `policy_security/` | `policy-security` | a forbidden-path write and a secret-bearing output are both BLOCKED |
| `resume_rollback/` | `resume-rollback` | a checkpointed run resumes (validate + continue) and a failed apply rolls back |
| `provider_fallback/` | `provider-fallback` | a faulty primary provider falls back to mock and a receipt is recorded |

## Deferred suites (stay framed, honestly NOT_MEASURED past 1.0-minimum)

`sdd-formal-feature`, `kg-retrieval-precision`, `memory-usefulness`,
`context-token-efficiency`, `plugin-compatibility` remain `DeclaredSuite` /
provider-gated and report `NOT_MEASURED` until their fixtures/providers land — never
a fake `MET` (build-rule #1).

## Runners

`opencontext_core.evaluation.golden.GoldenSuite` loads a fixture, runs it in a temp
copy, compares against `expected.json`, and returns a `BenchmarkSuiteReport`. The
suites are registered in `opencontext_core.evaluation.runner.build_default_runner`
and consumed by `release acceptance`.
