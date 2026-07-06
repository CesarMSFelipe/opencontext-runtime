# Test-suite reduction report (plan doc 2, Part II §18–§26)

Executed: 2026-07-06. Inputs: `artifacts/test-inventory.{json,md}` regenerated
from `scripts/test_inventory.py` immediately before the pass (the committed
inventory was stale after recent sprints). Every DELETE/MERGE/QUARANTINE
candidate was verified by reading the file against the §26.3 rules
(mock-only / duplicated-by-acceptance / dead-iteration artifact) before acting.
No file touched in the last 15 commits was a candidate.

## Before / after totals

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Test files | 793 | 793 | 0 |
| Test functions (static count) | 5134 | 5135 | +1 (TDD test for new inventory rule) |
| Files deleted | — | 0 | all 6 candidates failed §26.3 verification |
| Files merged | — | 0 | both MERGE pairs are stem collisions, not duplicates |
| Files quarantined | — | 1 (2 tests, now skip-marked) | `done_in_v1` archive |

Classification totals (after): KEEP_ACCEPTANCE 11, KEEP_CONTRACT 9,
KEEP_UNIT_CRITICAL 269, KEEP_INTEGRATION_BOUNDARY 454, KEEP_REGRESSION 40,
DELETE 6 (all reviewed → kept, see below), MERGE 3 (reviewed → left, see
below), QUARANTINE 1 (executed).

## Per-suite changes

Only suites that changed are listed; all other suites are untouched.

| Suite | Before | After | Change |
|-------|--------|-------|--------|
| done_in_v1 | 1 file / 2 tests | removed | moved to quarantine |
| quarantine | (did not exist) | 1 file / 2 tests | new home for archived/parked tests |
| unit | +0 | +1 test | TDD test for the `quarantine`-suite inventory rule |

## Deleted

(none)

## Merged

(none — see kept-despite-candidate below for why)

## Quarantined

- `tests/done_in_v1/test_validation_runner.py` →
  `tests/quarantine/test_done_in_v1_validation_runner.py`
  - Reason: archived v1 validation suite (inventory rule 3). Not flaky — each
    test re-runs all 17 behavioral probes via `tools/done_in_v1_probes.py` and
    rewrites `artifacts/done-in-v1-validation.json` during the run (slow,
    repo-mutating side effect inside the default run).
  - Mechanism: module-level `pytestmark = [pytest.mark.quarantine,
    pytest.mark.skip(reason="quarantined 2026-07-06: ...")]`. The `quarantine`
    marker is registered in `pyproject.toml`. Default pytest behavior for all
    other suites is unchanged (no `addopts` change); the file still collects
    but reports as skipped. To exclude quarantine from collection entirely in
    a custom run, use `-m "not quarantine"`; to re-verify the v1 probe
    contract, remove the skip mark and run the file explicitly.

## Kept despite DELETE candidacy (all 6 — reasons)

Inventory rule 5 ("mock imports AND no fs/subprocess") is a coarse static
heuristic; §26.3 requires that a file "only proves mocks" AND is duplicated or
dead. On reading, every candidate protects a public contract, a requirement,
or an algorithm edge case, and none is duplicated by
acceptance/golden/compat (verified by grep of those suites):

- `tests/cli/test_first_run_offer_gating.py` — public CLI contract: `--json`
  output purity and `--yes`/`--non-interactive` must never block on the
  first-run confirm prompt; documents the pty-CI regression rationale
  (isatty alone is insufficient). Not covered by acceptance.
- `tests/cli/test_memory_benchmark_seeding.py` — REQ-02c requirement test.
  Misdetected as mock-only: two of three tests run the REAL benchmark against
  an ephemeral temp-file DB (`db=None` path); the single patch only forces the
  zero-recall guard path. Protects exit-1-on-zero-recall + JSON field
  contract (`recall_at_5`, `seeded_records`).
- `tests/cli/test_mutation_cli.py` — CLI exit-code contracts: framework
  unavailable → exit 0 (graceful degradation relied on by
  `harness/phases.py`), no subcommand → exit 1, subparser registration.
- `tests/core/test_engram_provisioning.py` — live module (used by
  `opencontext_cli/main.py`, `commands/engram_cmd.py`,
  `agentic/install_plan.py`); protects the no-automated-install design
  decision and graceful degradation. Mocks only stub the environment probe
  `detect()`; the plan/install logic under test is real.
- `tests/core/test_hooks.py` — the `HookRegistry` class tests are pure logic
  with zero mocks (register/trigger/duplicate-guard and handler-failure
  isolation — an algorithm edge case); the mock flag comes only from the
  logger-assertion tests on default handlers. Module is used by
  `agents/orchestrator.py` and `operating_model/`.
- `tests/core/test_mcp_all_tools_enveloped.py` — schema-versioned public MCP
  contract (`opencontext.mcp_tool_result.v1`): denied/unknown/exception/success
  envelope statuses plus the backward-compat `error` key. No other suite
  (acceptance/golden/compat) covers `mcp_tool_result`.

## MERGE candidates left in place (not mechanical)

Both flagged pairs share only a normalized filename stem; they target
different modules and specs, so merging would combine unrelated tests:

- `tests/planning/test_foundation_reuse.py` (MetaPlanner reuse, SPEC
  MP-011/012/013) vs `tests/runtime/test_foundation_reuse.py` (runtime session
  reuse, RC-014/015/016) — different packages, zero overlap.
- `tests/runtime/test_compat_registry.py` (migration-ledger v2 flags,
  amendment A2) vs `tests/compat/test_compat_registry.py` (AdapterRegistry
  protocol, SPEC CL-001..004) — different modules; the compat side is
  KEEP_CONTRACT and untouchable anyway.

Optional follow-up (not done here): rename one file in each pair so the
duplicate-stem merge pass stops flagging them.

## Inventory tooling change

`scripts/test_inventory.py`: `ARCHIVED_SUITES` → `QUARANTINE_SUITES`
(`{"done_in_v1", "quarantine"}`) so files parked under `tests/quarantine/`
classify as QUARANTINE instead of falling through to boundary/unit rules.
Added TDD-first unit test `test_quarantine_suite_is_quarantine` in
`tests/unit/test_test_inventory.py`.

## Honesty note

The plan's 120–220-file reduction figure was directional. The fresh inventory
produced only 6 DELETE + 3 MERGE + 1 QUARANTINE candidates across 793 files,
and per-file verification reclassified all DELETE candidates as keepers
(signal over count). The executed reduction is therefore the quarantine of the
archived `done_in_v1` suite only. Deleting nothing from the DELETE list is the
faithful outcome of the classification rules as verified — not a skipped step.
