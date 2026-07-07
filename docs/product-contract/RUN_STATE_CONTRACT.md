# RUN_STATE_CONTRACT

Every stable command and every workflow (OC Flow, SDD, harness) terminates in exactly one of
the canonical final states below. No other final state is valid anywhere in the runtime.

Verified by: AC-009, AC-010, AC-011, AC-024, OC-001..OC-004, SMOKE-006..SMOKE-008.

## Canonical final states

| State | May exit 0? | Exit code | Meaning |
|---|---|---:|---|
| `passed` | Yes | 0 | Everything mandatory passed, with evidence persisted. |
| `failed` | No | 1 or 8 | A mandatory verification or gate failed (8 when tests/verification failed). |
| `blocked` | No | 1, 3 or 4 | Cannot continue: missing precondition, permissions, or policy (4 when policy/security blocked). |
| `needs_executor` | Per command | 5 | Task requires an executor/model and no productive one is available. |
| `needs_approval` | Per command | 4 | Policy requires human approval before continuing. |
| `needs_context` | No | 1 | The system could not build sufficient context for the task. |
| `needs_configuration` | No | 3 | Required configuration is missing or invalid; the report names the keys. |
| `not_applicable` | Yes | 0 | The command does not apply to this task/workspace and says why. |
| `cancelled` | No | 1 | Execution was interrupted by the user or the runtime. |

"Per command" states: read-only/status commands may exit 0 while reporting the state in JSON
(the state is the answer); workflow commands (`run`, `sdd apply`, `harness run`) must exit
non-zero (5 for `needs_executor`, 4 for `needs_approval`) so CI cannot mistake them for success.

## Rules

1. **No `passed` without evidence.** A workflow may report `passed` only when its mandatory
   gates passed and evidence is persisted in `.opencontext/runs/<run_id>/` (verification
   commands executed, gate results, diff when mutation was required). See `PRODUCT_CONTRACT.md`
   §Evidence requirements.
2. **State must match exit code.** The mapping above is normative; a command may not exit 0
   while reporting `failed`, nor exit non-zero while reporting `passed`.
3. **State appears in JSON.** In `--json` mode the envelope carries `"status": "<state>"`;
   errors additionally carry the error envelope (`CLI_CONTRACT.md`).
4. **No silent downgrades.** A missing executor is `needs_executor`, never `passed` with a
   note. A skipped verification is `blocked` or `failed`, never `passed`.
5. **`not_applicable` explains itself.** It must include a machine-readable reason (e.g. task
   is docs-only under TDD strict — see `TDD_STRICT_CONTRACT.md`).
6. **Interruptions are `cancelled`,** and resumable runs record resume metadata so
   `run --resume <session_id>/<run_id>` can continue without duplicating artifacts (AC-026).

## Expected states per situation (OC Flow reference)

| Situation | State |
|---|---|
| Task requires no change | `passed` with `mutation_required=false` |
| Task requires change, no executor | `needs_executor` |
| Executor mutates, verification passes | `passed` |
| Executor mutates, verification fails | `failed` |
| Policy demands human approval | `needs_approval` |
| Required config missing | `needs_configuration` |
| Context cannot be built | `needs_context` |
| Workspace/test-runner precondition missing | `blocked` |

> Current → Target: `needs_configuration` comes from the corrected plan and is part of the
> canonical catalog; current code paths that collapse it into `blocked` or `failed` must be
> migrated. `run.json` today persists a free-form `status` string; the target constrains it to
> this catalog and adds the exit-code derivation as a pure, unit-tested function.
