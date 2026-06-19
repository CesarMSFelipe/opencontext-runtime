# Test Quality Review — Senior QA Audit

Audit of the production test suite (`tests/`, **287 files / 1680 test functions**)
against four quality principles: safety-net vs happy-path, coupling to
implementation, mock/fake abuse, and coverage-vs-real-value. Evidence is
`file:line`; the standards below are the charter of the new **OC Tester** persona
(`personas.py`), which the agent system should auto-switch to when authoring tests.

---

## Headline metrics (the numbers that matter)

| Signal | Value | Read |
|--------|-------|------|
| Tests asserting an error/exception (`pytest.raises`) | **57 across 31 files** (~3% of 1680) | Overwhelmingly happy-path |
| Weak sole assertions (`is not None` / `isinstance`) | **177** | Shallow — pass even when behavior is wrong |
| Tautological assertions (`x in <all possible values>`, `None or not None`) | **4** confirmed | Always green — test nothing |
| `monkeypatch.setattr` on private/internal symbols | **40** (of 108 total patches) | Coupled to implementation |
| `Mock`/`MagicMock` | 19 (low) — but pervasive `Null*Store` + `MockLLMGateway` fakes | False confidence via architectural doubles |
| Subsystems on the hot path with ~no tests | `operating_model/` (1658 LOC, **0** test files), `learning/` (1606 LOC, 2) | Untested budget/quality logic |

The suite is large and mostly green, but green is cheap here: error paths are
barely exercised, many assertions can't fail, and several tests are bolted to
internals (we already paid for this — the `Prompt.ask`/`Confirm.ask` patches broke
on a pure refactor last week, and a pre-seeded `run.json` hid a real archive bug).

---

## Principle 1 — Safety net or happy path?

**Verdict: happy-path dominated.** Only ~3% of tests assert a failure mode.

- `harness/phases.py` ships **13 broad excepts and zero logger calls**; the matching
  phase tests never assert any of those error branches — they only run the success
  path and check it "didn't crash".
- The indexing hot loop swallows per-file parse failures silently
  (`indexing/project_indexer.py:82`) and **no test feeds it a malformed file** to
  prove a broken parser is surfaced (it isn't).
- `_post_run_update`'s memory harvest references a non-existent module
  (`harness/runner.py:503`) and was never caught because **no test asserts a run
  actually harvests memory** — only that `run()` returns.

**Critical examples**
- `tests/agents/test_concrete_agents.py:23` `test_runs_without_crash` — runs an
  agent and asserts only that keys exist in the result; no failure scenario.
- `tests/core/test_watch_service.py:159` `test_callback_error_does_not_crash` — the
  *name* promises error handling, but verify it asserts the error was actually
  swallowed-and-logged, not just that nothing raised.

---

## Principle 2 — Coupling (will it survive a refactor?)

**Verdict: a coupled minority that has already cost us.** 40 patches target
private/internal symbols.

- **Proven failure:** `tests/cli/test_setup_cli.py` and
  `tests/core/test_client_orchestrator_profiles.py` patched
  `setup_cmd.Confirm.ask` / `setup_cmd.Prompt.ask`. Routing prompts through one
  helper (a behavior-preserving refactor) **broke both tests** — textbook
  implementation coupling. They now patch `setup_cmd.prompts.*`, which is *less*
  coupled but still reaches into the module's import.
- `tests/configurator/test_personas.py` asserted `len({prompts}) == 3` — a
  hardcoded count that broke the moment a legitimate 4th persona was added. Fixed
  to `== len(_EXPECTED)`.
- `tests/core/test_runtime_v2.py:24` `assert hasattr(runtime, "_v2_enabled")` —
  asserts a **private attribute exists**, not any behavior. Renaming the field
  breaks the test though nothing observable changed.

---

## Principle 3 — Mock / fake abuse (false confidence)

**Verdict: low `unittest.mock`, but heavy architectural fakes that prove nothing.**

- `tests/harness/test_phases_v2_integration.py:79` runs `ArchivePhase` with
  `NullAgentMemoryStore` and asserts only `result.status in (PASSED, WARNING,
  FAILED)` — a fake store + a tautology. It exercises the phase against a no-op
  dependency and accepts any outcome.
- The agentic phase tests run under `MockLLMGateway`, so SPEC/DESIGN/TASKS emit
  static scaffolds; the tests assert the scaffold artifact exists — i.e. they test
  the *degraded* path and would stay green even if real LLM execution were wholly
  broken (it is — `_gateway_from_config` raises for real providers).
- The real dependencies here are cheap: a SQLite memory db and a KG db both run
  fine on `tmp_path`. There is no reason to fake them — the memory tests that DO
  use a real `tmp_path` SQLite (`tests/core/test_*memory*`) are the model to copy.

**Where mocks are fine:** the LLM provider and network are true external
boundaries — mock those. But then assert on the *effect* (artifact content,
persisted edit), not that a phase "ran".

---

## Principle 4 — Coverage vs real value

**Verdict: several tests are green decoration.**

- **The standout:** `tests/core/test_runtime_v2.py:36`
  ```python
  assert result is None or result is not None
  ```
  This is **always true** for any object. The test exercises `build_contract` and
  then asserts a tautology — it cannot fail. The same file guards every real
  assertion behind `if result is not None:`, so when v2 is disabled (the common
  case in CI) it asserts **nothing**.
- **Tautological status checks (3):** `tests/harness/test_runner_v2.py:35`,
  `tests/harness/test_phases_v2_integration.py:53,95`
  ```python
  assert result.status in (GateStatus.PASSED, GateStatus.WARNING, GateStatus.FAILED)
  ```
  That set is **every** possible status. The assertion passes regardless of
  outcome — a broken phase returning FAILED is "green".
- **177 shallow asserts** (`assert x is not None`) — acceptable as a *secondary*
  check, dangerous as the *only* one.

---

## Refactor suggestions (concrete before/after)

### R1 — Kill the tautology; pin the real classification
`tests/core/test_runtime_v2.py`
```python
# BEFORE — always green
result = runtime.build_contract("fix auth bug")
if result is not None:
    assert hasattr(result, "task_type") or hasattr(result, "risk_level")
assert result is None or result is not None

# AFTER — require the capability, assert the actual behavior
def test_build_contract_classifies_a_bug_task(self, tmp_path):
    runtime = _make_runtime(tmp_path)
    if not runtime._v2_enabled:
        pytest.skip("v2 planning unavailable in this environment")
    contract = runtime.build_contract("fix the auth login crash")
    assert contract is not None
    assert contract.task_type == TaskType.BUG_FIX          # pin the value
    assert contract.risk_level in (RiskLevel.NORMAL, RiskLevel.HIGH)
```

### R2 — Replace "status in all statuses" with the expected outcome + effect
`tests/harness/test_runner_v2.py`
```python
# BEFORE
result = runner.run("explore-only", "test task for runner v2")
assert result.status in (GateStatus.PASSED, GateStatus.WARNING, GateStatus.FAILED)

# AFTER — a valid project + explore-only must PASS and produce a context pack
result = runner.run("explore-only", "summarize the auth module")
assert result.status == GateStatus.PASSED
assert any(a.kind == "context-pack" for a in result.artifacts)   # real effect
assert result.run_id.startswith("explore-only-")
```

### R3 — Don't pre-seed the artifact the phase is supposed to produce
`tests/harness/test_phases_v2_integration.py` (this is exactly how the archive bug hid)
```python
# BEFORE — masks the bug: pre-creates the file the gate checks
(run_dir / "run.json").write_text("{}")
phase = ArchivePhase(...)
result = phase.run(state)
assert result.status in (PASSED, WARNING, FAILED)

# AFTER — let the phase produce it; assert it did and the gate passes
result = ArchivePhase(...).run(_FakeState(tmp_path))   # no pre-seed
assert (run_dir / "run.json").exists()                 # phase is self-contained
persisted = [g for g in result.gates if g.id == "artifact_persisted"]
assert persisted and all(g.status == GateStatus.PASSED for g in persisted)
```
*(This refactor is already applied as
`test_archive_self_persists_run_json_so_gate_passes` — use it as the template.)*

### R4 — Test behavior through the boundary, not by patching internals
`tests/cli/test_setup_cli.py`
```python
# BEFORE — coupled to the prompt implementation
monkeypatch.setattr(setup_cmd.Confirm, "ask", lambda *a, **k: False)   # broke on refactor

# AFTER — drive the real decision through the public seam (non-TTY returns the
# default), and assert the observable outcome: nothing was written.
monkeypatch.setattr("sys.stdin.isatty", lambda: False)   # boundary, not internals
cli_main._dispatch(_parse(["setup", "claude-code", "--scope", "global", ...]))
assert not (home / ".claude" / "CLAUDE.md").exists()
```

### R5 — Replace a fake store with an ephemeral real one + assert content
`tests/harness/test_phases_v2_integration.py`
```python
# BEFORE — Null store + tautology proves nothing about archiving
phase = ArchivePhase(config=..., memory_store=NullAgentMemoryStore())
assert result.status in (PASSED, WARNING, FAILED)

# AFTER — real SQLite store on tmp_path; assert the memory delta is real
store = BackendFactory.create_memory_store(config, tmp_path / ".storage/mem")
store.write(make_record("m1", MemoryLayer.EPISODIC, "run:x", "did X"))
result = ArchivePhase(config=..., memory_store=store).run(state)
delta = json.loads((run_dir / "memory_delta.json").read_text())
assert delta["records"]            # the phase actually captured memory
```

---

## Testing standards (OC Tester charter)

These are enforced by the `oc-tester` persona and should gate new tests:

1. **Safety net, not happy path** — every function with a failure mode gets a
   failure test (`pytest.raises` with type/message). A PR that adds a `raise`
   without a test for it is incomplete.
2. **Behavior, not implementation** — assert observable outcomes (returns,
   persisted state, artifacts). No asserting private (`_`) attributes; no
   patching private symbols. If a behavior-preserving refactor breaks the test,
   the test is wrong.
3. **Real over mocked** — use ephemeral real dependencies (`tmp_path` SQLite, real
   temp project/index). Mock only true external boundaries (network, paid LLM,
   clock) and assert on the real effect, not "the mock was called".
4. **Strong assertions** — pin exact expected values. Banned as a *sole*
   assertion: `is not None`, `isinstance`, `x in <all possible values>`,
   `assert True`, "does not crash". Ask: *would this fail if I broke the code?* If
   not, it's not a test.

**Litmus test for any existing test:** mutate the code it covers (flip a branch,
return early, drop a write). If the test still passes, delete or fix it.

---

## Priority cleanup list

| Severity | Test | Action |
|----------|------|--------|
| HIGH | `test_runtime_v2.py:36` tautology + conditional-only asserts | R1 — require v2, pin task_type |
| HIGH | 3× `status in (PASSED,WARNING,FAILED)` | R2 — assert the expected status + effect |
| HIGH | `operating_model/` (0 tests), `learning/` (thin) | Add behavior tests — both drive runtime budget/quality |
| MED | `test_phases_v2_integration.py` Null-store + pre-seed | R3/R5 — real store, no pre-seed |
| MED | 10× `*_does_not_crash` / `*_runs_without_crash` | Add a real outcome assertion to each |
| MED | indexing hot-loop silent swallow | Add a malformed-file test that asserts it's surfaced/counted |
| LOW | `hasattr(runtime, "_v2_enabled")` and similar | Assert behavior, not attribute presence |

---

## Appendix — good tests to emulate

- `tests/core/test_personalized_ranking_wired.py:53` — `assert ranked[0].id ==
  "a_authenticate", "query-personalized ranking not applied"` — pins the exact
  outcome with a failure message.
- The `tests/core/test_*memory*` suite uses a real `tmp_path` SQLite backend — the
  integration model the harness/agent tests should copy.
- `tests/core/test_prompts.py` + `tests/cli/test_no_raw_interactive_prompts.py`
  (recent) — test the degradation contract via the `_is_tty` boundary and guard a
  whole bug class without coupling to call sites.
