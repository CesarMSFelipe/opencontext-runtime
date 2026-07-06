# TDD_STRICT_CONTRACT

With `tdd.mode = strict`, TDD is a runtime guarantee, not a preference. A strict run cannot end
`passed` without machine-verified RED and GREEN evidence.

Verified by: AC-012, AC-013, TDD-001..TDD-008, SMOKE-009.

## RED → GREEN contract

For any implementation task under strict mode, the runtime must:

1. Detect or create a relevant new/modified test for the change.
2. Execute that test BEFORE the mutation.
3. Confirm it fails for the expected reason (failure signature captured).
4. Apply the mutation.
5. Execute the test AFTER the mutation.
6. Confirm it passes.
7. Run the minimal regression suite and confirm it passes.
8. Record RED and GREEN evidence in the run report.

Skipping any step means the run is not `passed`: exit code 6 (TDD strict violated) with the
standard error envelope (e.g. `error.code = "TDD_RED_NOT_PROVEN"`).

## RED evidence JSON

```json
{
  "red": {
    "command": "pytest tests/test_app.py::test_add -q",
    "exit_code": 1,
    "failed_tests": ["tests/test_app.py::test_add"],
    "failure_summary": "assert 0 == 3",
    "captured_at": "2026-07-06T00:00:00Z"
  }
}
```

## GREEN evidence JSON

```json
{
  "green": {
    "command": "pytest -q",
    "exit_code": 0,
    "passed_tests": 1,
    "failed_tests": 0,
    "captured_at": "2026-07-06T00:00:00Z"
  }
}
```

Both blocks live under `tdd` in `run.json`, alongside
`{"mode": "strict", "red_proven": true, "green_proven": true}` and an optional
`regression: {"command": "pytest -q", "exit_code": 0}` block.

## Policies

| Situation | Required behavior |
|---|---|
| Doc/config-only task with no applicable tests | `not_applicable` with a machine-readable justification — never fake RED/GREEN |
| No detectable test runner | `blocked` (or `needs_configuration` when a runner is configured but invalid) |
| Candidate test already passes before mutation | Not RED. Strict mode FAILS unless the declared task type is refactor/docs |
| Executor edits only tests when a functional change was required | Flagged suspicious; run cannot be `passed` without a functional diff |
| Mutation required but none detected | Not `passed` (see RUN_STATE_CONTRACT rules) |

## Integration rules

- OC Flow (`run`) and SDD (`sdd apply`) honor the same strict engine — one implementation, two
  entry points (TDD-007, TDD-008).
- Strict mode is configured via `tdd.mode` in `opencontext.yaml` (set by `init --tdd strict`)
  and propagates to harness and SDD without re-declaration (CFG-010).
- The RED detector is itself regression-tested: a deliberately broken detector must break the
  acceptance suite (AC-012/AC-013 act as the tripwire).

> Current → Target: strict mode exists as configuration (`init --tdd {ask,strict,off}`) and
> harness gating; the persisted RED/GREEN evidence JSON in `run.json` with `red_proven` /
> `green_proven` flags and the "already-passing test is not RED" enforcement are the freeze
> target for this contract.
