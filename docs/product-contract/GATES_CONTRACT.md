# GATES_CONTRACT

The mandatory gate catalog. Every OC Flow and harness run persists its gate results to
`.opencontext/runs/<run_id>/gates.json`; this contract freezes which gates exist, how they
are enforced, and the per-gate evidence rule. It formally supersedes the aspirational gate
lists in the close-out plans (see §Plan gate mapping).

Verified by: tests/harness/test_gate_catalog_contract.py (HARNESS-GATES-13),
tests/harness/test_gate_evidence_contract.py (HARNESS-CRIT-4), and the live catalog pin
tests/oc_flow/test_run_bundle_gates.py (AC-025).

## OC Flow mandatory gate catalog

Every OC Flow run evaluates exactly this catalog, in this persisted order
(`OC_FLOW_GATE_IDS`, `opencontext_core/oc_flow/run_bundle.py`). Gates that do not apply to
a run persist as `skipped` with an explanation — they are never dropped from the catalog.

```text
workspace_valid
config_valid
context_pack_created
executor_available
tdd_red_proven_if_strict
tdd_functional_change_if_required
mutation_performed_if_required
verification_executed
verification_passed
report_written
```

## Harness named gate catalog

The harness evaluates per-phase gates drawn from this named catalog (the gate classes in
`opencontext_core/harness/gates.py`). Phases may additionally record workflow-specific gate
results (e.g. dispatcher or shell-policy gates); every persisted record — named or
phase-specific — obeys the Evidence rule below.

```text
project_index_exists
context_pack_created
trace_id_created
security_scan_passed
token_budget
artifact_persisted
confidence
privacy
no_secret_leakage
included_sources_present
omissions_recorded
provider_policy_passed
policy_engine_passed
approval_required_for_writes
no_high_risk_exports
review_artifact_created
failing_test_exists
tests_pass
```

## Enforcement

- No run may terminate `passed`/`completed` while a mandatory gate is `failed`
  (`enforce_gates` in `oc_flow/run_bundle.py`; RUN_STATE_CONTRACT rules 1 and 4).
- Gate results persist to `.opencontext/runs/<run_id>/gates.json` for both workflows
  (PRODUCT_CONTRACT §Evidence requirements).

## Evidence rule

Every gate record persisted in `gates.json` MUST carry a non-empty, human-readable
`message` explaining the result. Writers enforce this at the persistence boundary: a gate
recorded without a message is backfilled with an honest fallback that names the gate id and
its status ("... without an evidence message") — the fallback admits missing detail rather
than inventing evidence. `metadata` and `evidence_refs` are additive detail fields and may
be empty.

## Plan gate mapping

The close-out plans list aspirational gate ids (DOC1
`docs/opencontext_plan_cierre_completo_sdd_tui_config_tests.md` "Gates obligatorias"; DOC2
`docs/opencontext_plan_funcional_cierre_y_tests_reales.md` §8.5 "Gates comunes"). This
contract supersedes those lists. Every plan id maps to the real mechanism that covers it:

| Plan gate id | Disposition | Covered by |
|---|---|---|
| `config_valid` | implemented | OC Flow gate `config_valid` |
| `workspace_valid` | implemented | OC Flow gate `workspace_valid` |
| `context_pack_created` | implemented | Gate `context_pack_created` (both catalogs) |
| `kg_available_or_declared_absent` | superseded | `run.json` explore/context metadata declares `kg_available` either way; KG absence degrades context, never blocks a run, so no pass/fail gate exists |
| `kg_available_or_explained` | superseded | Same mechanism as `kg_available_or_declared_absent` |
| `memory_policy_checked` | superseded | `run.json` `memory` block (`used`, `hits`, `new_candidates`, `requires_approval`) declares memory usage and approval policy per run (MEMORY_CONTRACT rule 4) |
| `memory_available_or_explained` | superseded | Same mechanism as `memory_policy_checked` |
| `executor_policy_checked` | implemented | `executor_available` (OC Flow) plus `provider_policy_passed` / `policy_engine_passed` (harness) |
| `provider_policy_passed` | implemented | Harness gate `provider_policy_passed` |
| `approval_checked` | implemented | Harness pre-gate `approval_required_for_writes` |
| `approval_granted_if_required` | implemented | Harness pre-gate `approval_required_for_writes` |
| `tdd_red_required_if_strict` | implemented | `tdd_red_proven_if_strict` (OC Flow) plus `failing_test_exists` (harness strict RED) |
| `tdd_red_proven_if_strict` | implemented | Same gates as `tdd_red_required_if_strict` |
| `mutation_required_if_task_requires_change` | implemented | `mutation_performed_if_required` (fails when a mutation task produced no edits) |
| `mutation_detected_if_required` | implemented | `mutation_performed_if_required` plus `tdd_functional_change_if_required` |
| `mutation_performed_if_required` | implemented | OC Flow gate `mutation_performed_if_required` |
| `verification_command_executed` | implemented | `verification_executed` |
| `verification_executed_if_required` | implemented | `verification_executed` (persists as `skipped` when not required) |
| `verification_passed` | implemented | `verification_passed` plus `tests_pass` (harness strict GREEN) |
| `verification_passed_if_required` | implemented | Same gates as `verification_passed` |
| `json_contract_valid` | superseded | The CLI JSON contract is enforced by the acceptance suite (AC-024, CLI_CONTRACT), not by a per-run gate |
| `evidence_complete` | superseded | Run-bundle writer plus `enforce_gates` plus AC-025 evidence assertions; per-gate evidence is enforced by the Evidence rule above |
| `memory_delta_valid` | superseded | `memory_delta.json` is a mandatory run artifact (PRODUCT_CONTRACT §Evidence requirements); its shape is pinned by writer tests, not a separate gate |
| `graph_delta_valid` | superseded | `graph_delta.json` — same mechanism as `memory_delta_valid` |
| `report_written` | implemented | OC Flow gate `report_written` |

Adding, removing, or renaming a gate in code requires updating this contract in the same
change — the HARNESS-GATES-13 pinning tests fail otherwise.
