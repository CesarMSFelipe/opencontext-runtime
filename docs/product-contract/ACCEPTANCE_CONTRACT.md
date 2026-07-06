# ACCEPTANCE_CONTRACT

The acceptance suite is black-box: it invokes the real `opencontext` binary, never imports
runtime modules, and asserts on observable behavior (filesystem, JSON, exit codes, artifacts).
It is the primary measure of product completion.

Verified by: this file DEFINES the acceptance IDs referenced by every other contract.

## Full acceptance suite (AC-001..AC-030)

| ID | Scenario | Priority |
|---|---|---:|
| AC-001 | `version --json` returns the real version as clean JSON. | P0 |
| AC-002 | `doctor --json` is parseable and mixes no human text into stdout. | P0 |
| AC-003 | Workspace `init` / `install` creates the expected files. | P0 |
| AC-004 | `status --json` detects a valid workspace. | P0 |
| AC-005 | `index --json` produces an index and a minimal knowledge graph. | P0 |
| AC-006 | `knowledge-graph search` finds a symbol and its related test. | P0 |
| AC-007 | `pack` (JSON output) includes relevant files and excludes irrelevant ones. | P0 |
| AC-008 | `pack` reports token budget and KG usage metrics. | P0 |
| AC-009 | `run` without an executor returns `needs_executor`, not `passed`. | P0 |
| AC-010 | `run` with a correct executor mutates the file and passes verification. | P0 |
| AC-011 | `run` with a wrong executor returns `failed` and a non-zero exit code. | P0 |
| AC-012 | TDD strict fails when there is no RED test. | P0 |
| AC-013 | TDD strict passes only with RED → GREEN demonstrated. | P0 |
| AC-014 | `sdd new` creates a cycle and its initial artifacts. | P0 |
| AC-015 | `sdd propose/spec/design/tasks` consume and produce connected artifacts. | P0 |
| AC-016 | `sdd apply/verify` execute real gates. | P0 |
| AC-017 | `memory save/search/get` works. | P1 |
| AC-018 | A second run retrieves approved memory and reports it as used. | P0 |
| AC-019 | `memory compact` reduces old entries without deleting protected memory. | P1 |
| AC-020 | Incremental KG indexing updates nodes after a file change. | P1 |
| AC-021 | Under token pressure, `pack` compresses and preserves protected spans. | P0 |
| AC-022 | `uninstall --scope workspace --purge --verify` removes managed workspace residue. | P0 |
| AC-023 | Product uninstall `--purge --verify` uses the manifest and cleans the managed install. | P0 |
| AC-024 | Common errors are actionable and return the stable JSON error envelope. | P1 |
| AC-025 | The report bundle contains run manifest, commands, diffs, verification, memory delta, and graph delta. | P0 |
| AC-026 | `run --resume` continues an interrupted run without duplicating artifacts. | P1 |
| AC-027 | Policy blocks dangerous commands by default. | P0 |
| AC-028 | Secret redaction strips tokens/secrets from reports and memory. | P0 |
| AC-029 | The release artifact contains no `.git`, `.venv`, caches, or local state. | P0 |
| AC-030 | The acceptance harness passes against a cleanly installed package. | P0 |

## Smoke suite (SMOKE-001..010) — runs on every PR

| ID | Scenario |
|---|---|
| SMOKE-001 | `version` emits clean JSON. |
| SMOKE-002 | `doctor` output is parseable. |
| SMOKE-003 | Workspace `init` + `status` work. |
| SMOKE-004 | `index` + `knowledge-graph search` work. |
| SMOKE-005 | `pack` includes the expected symbol/test. |
| SMOKE-006 | `run` without executor → `needs_executor`. |
| SMOKE-007 | `run` with correct test stub executor → `passed`. |
| SMOKE-008 | `run` with wrong test stub executor → `failed`. |
| SMOKE-009 | TDD strict without RED → fails. |
| SMOKE-010 | `uninstall --scope workspace --purge --verify` leaves no managed residue. |

## Execution modes

```bash
# Against the local binary/checkout
pytest tests/acceptance -q --oc-bin ./dist/opencontext.pyz

# Against the installed package, as a real user
python -m venv /tmp/oc-acceptance-venv
/tmp/oc-acceptance-venv/bin/pip install opencontext-cli==X.Y.Z
pytest tests/acceptance -q --oc-bin /tmp/oc-acceptance-venv/bin/opencontext
```

Rules: fixtures are small and committed (`tests/acceptance/fixtures/`); tests never depend on
developer-local state; every failure message names the contract it broke.

## Timing budgets

| Suite | Size | Budget |
|---|---:|---:|
| Smoke (every PR) | 8–12 tests | < 60 s |
| Full acceptance (main/release) | 25–35 tests | < 5 min |

> Current → Target: `tests/acceptance/` with `--oc-bin` does not exist yet; today's suite is
> in-process pytest. This file freezes the scenario list so the harness can be built against it
> without renegotiating scope. Suite growth cap: no new AC IDs until AC-001..AC-030 pass.
