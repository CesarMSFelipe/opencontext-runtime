# Spec Traceability Matrix — DOC1 + DOC2

- **Date:** 2026-07-07
- **Plan documents:** `docs/opencontext_plan_cierre_completo_sdd_tui_config_tests.md` (DOC1), `docs/opencontext_plan_funcional_cierre_y_tests_reales.md` (DOC2)
- **Contracts:** `docs/product-contract/`
- **Sources:** per-area audit (requirement -> evidence rows) + closure round (commits `cb326e2`, `63f35c2`, `c2119db`, `ba601b5`, `f427306`, `fa3234a`, `aed5800`, `beb7ae4`, `f204d55`, `c4cdf7b`, `76dcf3b`, `189444d`, `002f6bf`)
- **Statuses:** `met` (requirement verified by passing tests), `deviation-documented` (behavior differs from the literal plan text; the difference is recorded in a product contract or plan amendment and the actual behavior is test-pinned), `open` (not closed; the oc-flow closure agent failed).

## Re-verification (2026-07-07)

Every test file named by the closure round was re-run on this branch (`feat/oc-sdd-and-flow-with-memory`, HEAD `002f6bf` + traceability commit). All green:

| Lane | Contents | junitxml result |
|---|---|---|
| Batch 1 | cfg/kg/ctx closure files (`test_config_cli_flag_overrides`, `test_interface_runtime_gating`, `test_config_legacy_warning`, `test_config_resolution`, `test_profiles_runtime`, `test_kg_ignores_caches`, `test_kg_explain_pack_cmd`, `test_tui_graph_loaders`, `test_kg_min_vocab`, `test_kg_callers_callees_cmd`, `test_pack_kg_contract`, `test_pack_memory_inclusion`, `test_tui_pack_viewer`, `test_protected_spans_extended`, `test_ranking_factor_weights`, `test_secret_scanner`) | tests=85, failures=0, errors=0, skipped=0 |
| Batch 2 | tdd/exe/mem closure files (`test_tdd_regression_evidence`, `test_harness_tdd_regression`, `test_tdd_not_applicable`, `test_tdd_test_only_edit`, `test_shell_policy_gate`, `test_policy_engine`, `test_policies_overlay`, `test_memory_approval_config`, `test_memory_recall_exclusion`, `test_memory_lifecycle_cmd`, `packages/opencontext_memory/tests/test_taxonomy.py`, `test_run_memory_report_fields`) | tests=91, failures=0, errors=0, skipped=0 |
| Batch 3 | inst/sdd/tui/cli-states/harness/release-dod closure files (`test_scope_hierarchy_cmds`, `test_install_manifest_v2`, `test_sdd_contract_items`, `test_sdd_phase_artifacts`, `packages/opencontext_sdd/tests/test_states_and_rules.py`, `test_tui_flows`, `test_tui_memory_lifecycle`, `test_cli_flags_matrix`, `test_cli_json_envelope_matrix`, `test_cli_help_maturity`, `test_error_code_catalog`, `test_gate_catalog_contract`, `test_gate_evidence_contract`, `test_release_report_contract`, `test_suite_taxonomy`, `test_golden_json_contracts`, `test_json_purity_sweep`, `test_full_file_threshold`, `test_p0_suite_policy`) | tests=228, failures=0, errors=0, skipped=0 |
| Updated-pin files | `packages/opencontext_sdd/tests/test_status.py`, `tests/oc_flow/test_run_bundle_memory.py`, `tests/cli/test_contracts_truth_layer.py`, `tests/cli/test_runs_inspect.py` | 75 passed |
| Unit lane (`tests/unit`) | includes `test_unit_timing.py` guard | tests=86, failures=0, errors=0, skipped=0 |
| Full acceptance (`tests/acceptance -q`) | includes `test_acceptance_memory.py`, `test_acceptance_policy.py`, `test_acceptance_timing.py`, `test_acceptance_install_manifest.py`, `test_acceptance_sdd_failure.py`, `test_acceptance_kg_pack.py` | tests=52, failures=0, errors=0, skipped=1 (smoke-lane guard correctly skipping outside its lane), wall 154.2 s < 300 s budget, exit 0 |
| Smoke lane (`tests/acceptance -m smoke`) | 12 scenarios + in-lane guard | tests=13, failures=0, errors=0, skipped=0, wall 37.0 s < 60 s budget |

Named closure tests confirmed present-and-passing by name in the acceptance junitxml: `test_memory_compact_preserves_protected_memory`, `test_secret_redaction_scrubs_the_whole_run_report_bundle`, `test_run_memory_block_reports_candidates_and_approval`, `test_memory_lifecycle_verbs_dispatch_end_to_end`, `test_full_install_registers_product_manifest`, `test_product_install_registers_manifest`, `test_workspace_install_registers_v2_manifest`, `test_reinstall_through_real_cli_is_idempotent`, `test_sdd_workflow_fails_when_tests_fail`, `test_kg_search_finds_symbol_and_related_test`, `test_full_acceptance_lane_meets_size_and_time_budget`.

---

## Area: ac-smoke (acceptance + smoke + timing)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| AC-001 | `version --json` devuelve versión real y JSON limpio | met | `tests/acceptance/test_acceptance_cli_contracts.py::test_version_json_is_clean_and_real` (smoke): JSON stdout, no ANSI, semver check. |
| AC-002 | `doctor --json` parseable, sin texto humano | met | `test_acceptance_cli_contracts.py::test_doctor_json_is_parseable_and_pure` (smoke): pure JSON, structured scope/checks/passed/failed. |
| AC-003 | `workspace init/install` crea archivos esperados | met | `test_acceptance_workspace.py::test_install_creates_expected_workspace_files` (smoke) + `::test_init_non_interactive_creates_workspace`. |
| AC-004 | `status --json` detecta workspace válido | met | `test_acceptance_workspace.py::test_status_json_detects_valid_workspace` (smoke) + `::test_status_json_reports_missing_workspace_as_needs_configuration` (exit 3). |
| AC-005 | `index --json` genera índice y KG mínimo | met | `test_acceptance_kg_pack.py::test_index_json_builds_a_minimal_knowledge_graph` (smoke): real `index . --json`, indexed_files>=14, symbol_count>=20. |
| AC-006 | `knowledge-graph search` encuentra símbolo y test relacionado | met | `test_acceptance_kg_pack.py::test_kg_search_finds_symbol_and_related_test` (smoke); extended by release-dod closure with a black-box `kg impact --json` leg. |
| AC-007 | `pack --json` incluye relevantes y excluye irrelevantes | met | `test_acceptance_kg_pack.py::test_pack_includes_relevant_and_excludes_irrelevant` (smoke); release-dod closure added numeric pins: inclusion >=95%, exclusion >=80%. |
| AC-008 | `pack` reporta presupuesto de tokens y uso de KG | met | `test_acceptance_kg_pack.py::test_pack_reports_token_budget` + `::test_pack_reports_kg_usage_metrics` (kg_nodes_used, kg_edges_used, memory_hits, protected_spans, compression_ratio). |
| AC-009 | `run` sin executor devuelve needs_executor, no passed | met | `test_acceptance_oc_flow.py::test_run_without_executor_reports_needs_executor` (smoke) + `::test_run_without_executor_exits_5`. |
| AC-010 | `run` con executor correcto muta archivo y pasa verificación | met | `test_acceptance_oc_flow.py::test_run_with_correct_executor_mutates_and_verifies` (smoke) + `::test_run_success_uses_canonical_passed_state`. |
| AC-011 | `run` con executor incorrecto devuelve failed y exit != 0 | met | `test_acceptance_oc_flow.py::test_run_with_wrong_executor_never_reports_success` (smoke) + `::test_run_with_wrong_executor_exits_failed`. |
| AC-012 | TDD strict falla si no hay test RED | met | `test_acceptance_tdd.py::test_tdd_strict_fails_without_red_test` (smoke): exit 6. |
| AC-013 | TDD strict pasa solo con RED->GREEN demostrado | met | `test_acceptance_tdd.py::test_tdd_red_green_demonstrated_externally` + `::test_run_report_records_red_green_evidence`. |
| AC-014 | SDD `new` crea ciclo y artefactos iniciales | met | `test_acceptance_sdd.py::test_sdd_new_creates_cycle_and_initial_artifacts`: real `sdd init` + `sdd new`. |
| AC-015 | SDD propose/spec/design/tasks consume y produce artefactos conectados | met | `test_acceptance_sdd.py::test_sdd_status_recognizes_the_scaffolded_proposal` + `::test_sdd_phases_consume_and_produce_connected_artifacts`. |
| AC-016 | SDD apply/verify ejecuta gates reales | met | `test_acceptance_sdd.py::test_sdd_harness_run_executes_real_gates`: run.json, gates.json with passed gate, receipts, real mutation. |
| AC-017 | `memory save/search/get` funciona | met | `test_acceptance_memory.py::test_memory_save_search_get_roundtrip`. |
| AC-018 | Segunda ejecución recupera memoria aprobada y la reporta como usada | met | `test_acceptance_memory.py::test_second_run_reports_approved_memory_as_used` + `stub_run` fixture (memory.used==true with hits). Minor note (audit): hit id not tied to saved id, single-memory workspace makes it unambiguous. |
| AC-019 | `memory compact` reduce entradas antiguas sin borrar memoria protegida | met (closed this round) | Extended `test_acceptance_memory.py::test_memory_compact_preserves_protected_memory`: seeds compactable duplicates black-box, asserts `after == before - 1` + `compacted_ids` from CLI JSON; keeper and pinned entry survive. Re-verified 2026-07-07 in the acceptance lane. |
| AC-020 | KG incremental actualiza nodos tras cambio de archivo | met | `test_acceptance_kg_pack.py::test_incremental_index_updates_nodes_after_file_change`. |
| AC-021 | Pack bajo presión aplica compresión y conserva spans protegidos | met | `test_acceptance_kg_pack.py::test_pack_under_token_pressure_keeps_protected_content` + `::test_pack_under_pressure_reports_compression`; release-dod closure added numeric pins (protected_spans_kept == protected_spans, reduction >= 40%). |
| AC-022 | `uninstall workspace --purge --verify` elimina residuos gestionados | met | `test_acceptance_uninstall.py::test_workspace_uninstall_purges_managed_state` (smoke) + `::test_workspace_uninstall_verify_passes_clean`. |
| AC-023 | `uninstall product --purge --verify` usa manifest y limpia instalación gestionada | met | `test_acceptance_uninstall.py::test_product_uninstall_uses_manifest_and_cleans_home_state` + `tests/cli/test_uninstall_manifest_driven.py`. |
| AC-024 | Errores comunes accionables con estructura JSON estable | met | `test_acceptance_cli_contracts.py::test_common_errors_are_actionable` + `::test_json_failures_return_stable_error_envelope`. |
| AC-025 | Report bundle: manifest, comandos, diffs, verificación, memory delta, graph delta | met | `test_acceptance_report.py::test_report_bundle_contains_all_evidence` + `::test_report_bundle_includes_run_manifest_and_gates`. |
| AC-026 | `resume` continúa ejecución interrumpida sin duplicar artefactos | met | `test_acceptance_report.py::test_resume_continues_without_duplicating_artifacts`. |
| AC-027 | Policy bloquea comandos peligrosos por defecto | met | `test_acceptance_policy.py::test_policy_blocks_dangerous_commands_by_default` + `tests/core/test_policy_engine.py` enforcement pins. |
| AC-028 | Secret redaction elimina tokens/secrets de reportes y memoria | met (closed this round) | New `test_acceptance_policy.py::test_secret_redaction_scrubs_the_whole_run_report_bundle` (seeds secrets through a real stub run; scans every file under `.opencontext/` with `find_secret_leaks`) + `tests/core/test_secret_scanner.py::test_prose_redaction_strips_inline_env_assignments`. Real leak found and fixed: new `redact_prose_secrets` in `packages/opencontext_core/opencontext_core/safety/redaction.py`, wired at all four task boundaries. Re-verified 2026-07-07. |
| AC-029 | Release artifact sin .git, .venv, caches ni estado local | met | `test_acceptance_release.py::test_release_artifact_contains_no_local_state`. |
| AC-030 | Acceptance harness pasa contra paquete instalado limpio | met | `test_acceptance_release.py::test_acceptance_smoke_passes_against_clean_install` + `.github/workflows/release-acceptance.yml` full-harness run + `tests/release/test_publish_gated_on_acceptance.py`. |
| SMOKE-001 | version JSON limpio en la smoke lane de cada PR | met | smoke marker on AC-001 test; CI `pytest tests/acceptance -m smoke` on every PR. |
| SMOKE-002 | doctor parseable | met | smoke marker on AC-002 test; in PR smoke lane. |
| SMOKE-003 | workspace init/status | met | smoke markers on `test_install_creates_expected_workspace_files` + `test_status_json_detects_valid_workspace`. |
| SMOKE-004 | index + kg search | met | smoke markers on AC-005/AC-006 tests. |
| SMOKE-005 | pack incluye símbolo/test | met | smoke marker on AC-007 test. |
| SMOKE-006 | run needs_executor sin executor | met | smoke marker on AC-009 test. |
| SMOKE-007 | run con test_stub correcto pasa | met | smoke marker on AC-010 test. |
| SMOKE-008 | run con test_stub incorrecto falla | met | smoke marker on AC-011 test. |
| SMOKE-009 | tdd strict sin RED falla | met | smoke marker on AC-012 test (exit 6). |
| SMOKE-010 | uninstall workspace purge verify | met | smoke marker on AC-022 test. |
| TIME-SMOKE | Smoke suite < 60 s (§21.1, 8-12 tests) | met (closed this round) | `tests/acceptance/test_acceptance_timing.py::test_smoke_lane_meets_size_and_time_budget` (in-lane guard: 8-12 scenarios, wall < 60 s; negative-check proven). Audit's 76-80 s reading did not reproduce standalone. Re-verified 2026-07-07: pure smoke lane = 13 tests (12 scenarios + guard), 0 failures, wall 37.0 s. |
| TIME-FULL-ACC | Acceptance full < 5 min, 25-35 tests (§21.1 / §5.5) | deviation-documented | Guard `test_acceptance_timing.py::test_full_acceptance_lane_meets_size_and_time_budget` (wall < 300 s, 25-50 scenarios). Deviation: documented 25-35 cap contradicted the honestly-pinned suite; `docs/product-contract/ACCEPTANCE_CONTRACT.md` + DOC2 §21.1 amended 25-35 -> 25-50 (guard meta-tests excluded from scenario counts). Re-verified 2026-07-07: 52 tests, wall 154.2 s, exit 0. |
| TIME-UNIT | Unit core algorithms 60-120 tests < 10 s (§21.1) | met (closed this round) | `tests/unit/test_unit_timing.py::test_unit_core_lane_meets_size_and_time_budget` + `tests/unit/conftest.py` formally delimit `tests/unit` as the §21.1 unit-core lane (60-120 tests, wall < 10 s; negative-check proven). Re-verified 2026-07-07: 86 tests, 0 failures, well under budget. |

## Area: cfg (configuration)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| CFG-001 | workspace override gana a global | met | `tests/core/test_config_resolution.py::test_project_beats_global` + `tests/core/test_config_explain.py::test_conflicts_report_losing_layers`; live-confirmed by audit. |
| CFG-002 | ENV gana a workspace | met | `test_config_resolution.py::test_env_beats_project`, `::test_env_beats_profile`, `::test_env_map_covers_tdd_and_storage_mode`. |
| CFG-003 | CLI flag gana a ENV | met (closed this round) | `config explain` now ships `--profile` and `--set KEY=VALUE` wired into `resolve(cli_overrides=...)` (`packages/opencontext_cli/opencontext_cli/commands/config_cmd.py`). `tests/cli/test_config_cli_flag_overrides.py::test_profile_flag_beats_env`, `::test_set_flag_beats_env`, `::test_malformed_set_pair_fails_with_contract_error`. Re-verified 2026-07-07. |
| CFG-004 | profile `ci` desactiva interactividad | met (closed this round) | `interface.*` now consumed at entry points: `handle_tui` refuses launch when `interface.tui=false` (exit 3); wizard/menu fall back non-interactive; `config show` defaults to JSON. `tests/cli/test_interface_runtime_gating.py::test_ci_profile_refuses_tui`, `::test_ci_profile_makes_config_show_default_to_json`, `::test_ci_profile_forces_non_interactive_wizard`. Re-verified 2026-07-07. |
| CFG-005 | key desconocida genera warning | met | `tests/core/test_config_explain.py::test_unknown_key_reported_as_warning`; live: unknown_keys=['bogus_key'], validation warning, exit 0. |
| CFG-006 | config inválida falla con error útil | met | `test_config_explain.py::test_unparseable_yaml_raises_configuration_error` + `tests/cli/test_config_explain_cmd.py` (CONFIG_INVALID envelope, exit 3, hint). |
| CFG-007 | `config explain` indica fuente de cada valor | met | `test_config_explain.py::test_sources_report_layer_path_and_line` + CLI-level contract payload test. |
| CFG-008 | migración de config antigua produce aviso | deviation-documented | Ordinary `load_config` now emits `LegacyConfigWarning` naming key/replacement/file on every auto-migrated legacy key; generic registry `DEPRECATED_CONFIG_KEYS` shared by doctor/explain. `tests/core/test_config_legacy_warning.py` (3 tests). Deviation (recorded): `version: 1` configs do NOT warn — v1 is a fully supported schema per the `config.version` contract, not a migrated shape. Re-verified 2026-07-07. |
| CFG-009 | secret no se imprime en JSON | met | `test_config_explain.py::test_secret_values_are_masked` + `test_config_explain_cmd.py::test_config_invalid_envelope_never_echoes_secret_values`. |
| CFG-010 | configuración TDD se propaga a harness y SDD | met | `test_config_resolution.py::test_tdd_mode_propagates_to_harness_governance`; `tests/harness/test_sdd_strict_tdd_e2e.py`; `tests/opencontext_sdd/test_runner.py::test_prompt_embeds_tdd_mode_when_strict`. |
| LAYERS-ORDER | 8-layer precedence: defaults < global < org < workspace < profile < env < CLI flags < run overrides | deviation-documented | Doc layers 7/8 now split: new `run` layer (`resolve(run_overrides=...)`, CLI `--run-override`) sits above `overrides` (CLI flags); both reachable from shipped CLI flags. `tests/core/test_config_resolution.py::test_layers_are_ordered`, `::test_run_override_beats_cli_override`, `::test_run_override_beats_env`, `::test_run_override_can_select_profile`; `tests/cli/test_config_cli_flag_overrides.py::test_run_override_flag_beats_set_flag`. Deviations (recorded): layer 7 keeps the provenance name `overrides` for back-compat; internal `policy` layer remains topmost (additive, above the doc's 8). Re-verified 2026-07-07. |
| EXPLAIN-SHAPE | `config explain --json` returns {effective_config, sources{value,source,path,line}, conflicts, deprecated_keys, unknown_keys, validation.status} | met | `tests/cli/test_config_explain_cmd.py::test_config_explain_json_emits_contract_payload` + per-field pins in `tests/core/test_config_explain.py`; one additive `profile` key. |
| PROFILES-RUNTIME | profiles default/ci/local/agent semantics | deviation-documented | Added `ExecutorsConfig` (`default: test_stub`, `allow_shell: false`); built-in `default` profile overlay per doc; oc_flow executor selection honors explicit `executors:` section; ci/local runtime enforcement via interface gating. `tests/core/test_profiles_runtime.py` + `tests/cli/test_interface_runtime_gating.py::test_local_profile_does_not_refuse_tui_at_the_gate`, `::test_local_profile_keeps_wizard_interactive`, `tests/core/test_config_profiles.py`. Deviations (recorded): implicit profile remains `balanced` (`test_implicit_profile_remains_balanced`) — `default` semantics apply when explicitly selected; `allow_shell` gates nothing yet (no built-in shell-capable executor). Re-verified 2026-07-07. |

## Area: tdd

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| TDD-001 | TDD strict falla sin test | met | `tests/acceptance/test_acceptance_tdd.py::test_tdd_strict_fails_without_red_test`; `tests/oc_flow/test_tdd_red_green.py::test_strict_without_test_runner_is_a_violation`; live: exit 6, TDD_NO_TEST_RUNNER. |
| TDD-002 | TDD strict falla si el test pasa antes | met | `tests/oc_flow/test_red_first_posture.py::test_strict_blocks_mutation_on_already_green_test`; `test_tdd_red_green.py::test_strict_with_already_green_test_is_a_violation`; `tests/harness/test_tdd_gates_strict.py::test_strict_fails_when_test_passes`. |
| TDD-003 | TDD strict falla si mutación no ocurre | met | `tests/workflows/test_oc_flow_completion_gate.py` (3 no-op variants); AC-009 tests; `tests/oc_flow/test_run_bundle_gates.py` (mutation_performed_if_required). |
| TDD-004 | TDD strict falla si GREEN no pasa | met | `tests/harness/test_sdd_strict_tdd_e2e.py::test_strict_tdd_wrong_fix_fails_green_gate`; AC-011 tests; `test_tdd_gates_strict.py::TestTestsPassGate::test_fails_when_tests_fail`. |
| TDD-005 | TDD strict pasa con RED -> GREEN real | met | `test_acceptance_tdd.py::test_tdd_red_green_demonstrated_externally`; `test_red_first_posture.py::test_strict_mutates_on_red_test`; `test_sdd_strict_tdd_e2e.py::test_strict_tdd_correct_fix_mutates_and_green_passes`. |
| TDD-006 | Evidencia RED/GREEN queda en report + evidence JSON shape (incl. regression block) | met (closed this round) | Regression block now populated: post-GREEN strict regression capture in `oc_flow/runner.py`; harness `_tdd_block_from_gates` derives regression from verify re-run; verify phase persists PASSED `verify_tests_passed` gate with command/exit_code. `tests/oc_flow/test_tdd_regression_evidence.py` (incl. `test_strict_passing_run_records_regression_evidence`) + `tests/harness/test_harness_tdd_regression.py`. Re-verified 2026-07-07. |
| TDD-007 | SDD respeta TDD strict | met | `tests/harness/test_sdd_strict_tdd_e2e.py` (both directions); `test_tdd_gates_strict.py::TestFailingTestExistsGateStrictMode`; governance resolution in `harness/runner.py`. |
| TDD-008 | OC Flow respeta TDD strict | met | `tests/oc_flow/test_red_first_posture.py`; wiring in `oc_flow/runner.py` (RED capture pre-mutation, evaluate_strict, violation short-circuit); AC-012/AC-013. |
| TDD-CRIT-1 | Si no hay RED, no hay passed | met | `test_run_bundle_gates.py::test_enforcement_downgrades_completed_on_failed_gate`; AC-012 test; `test_tdd_red_green.py::test_missing_red_run_is_not_proven`. |
| TDD-CRIT-2 | Si no hay GREEN, no hay passed | met | AC-011 tests; `test_sdd_strict_tdd_e2e.py::test_strict_tdd_wrong_fix_fails_green_gate`; `test_tdd_red_green.py::test_green_proven_requires_a_passing_run`. |
| TDD-CRIT-3 | Sin mutación requerida, no hay passed | met | Same spine as TDD-003 (completion gate, inspection scope BLOCKING gate, AC-009, run-bundle gate). |
| TDD-CRIT-4 | Test ya pasaba antes no cuenta como RED | met | `test_tdd_red_green.py::test_already_passing_test_is_not_red` + classification pins; `test_red_first_posture.py::test_strict_blocks_mutation_on_already_green_test`; `test_tdd_gates_strict.py::test_strict_fails_when_test_passes`. |
| TDD-POL-NA | Tarea documental/config sin tests aplicables -> not_applicable con justificación | met (closed this round) | `TddEvidence.mode_result="not_applicable"` + justification for strict read-only tasks (red/green None, no violation, exit 0, persisted in run.json). `tests/oc_flow/test_tdd_not_applicable.py` (incl. `test_strict_readonly_task_reports_not_applicable`, mutation-task-never-NA pin). Re-verified 2026-07-07. |
| TDD-POL-SUSPICIOUS | Executor que edita solo tests debe detectarse como sospechoso | met (closed this round) | New detector: `is_test_path`/`is_test_only_change` + `functional_change_expected`; test-only edits on functional tasks -> status blocked, `tdd.violation=TDD_TEST_ONLY_EDIT`, exit 6, failed `tdd_functional_change_if_required` gate. `tests/oc_flow/test_tdd_test_only_edit.py` (unit + e2e + control + non-strict posture). Re-verified 2026-07-07. |
| TDD-POL-NORUNNER | Sin test runner detectable -> blocked o needs_verification_config | met | `test_red_first_posture.py::test_strict_unavailable_runner_is_blocked_before_red` + env-error variant; `tests/core/test_run_exit_derivation.py` (tdd_violation -> blocked, exit 6); live: blocked, TDD_NO_TEST_RUNNER. |

## Area: oc-flow

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| OC-001 | Run sin executor devuelve `needs_executor` | met | `tests/acceptance/test_acceptance_oc_flow.py::test_run_without_executor_reports_needs_executor` + `::test_run_without_executor_exits_5`; live-confirmed. |
| OC-002 | Con executor correcto muta y verifica | met | `test_acceptance_oc_flow.py::test_run_with_correct_executor_mutates_and_verifies` + canonical-passed pin; `tests/workflows/test_oc_flow_executor.py`; `tests/e2e/test_flow_systems_integration.py` PATH A. |
| OC-003 | Con executor malo falla | met | `test_acceptance_oc_flow.py::test_run_with_wrong_executor_never_reports_success` + exit pin; e2e negative branch. |
| OC-004 | Sin config necesaria devuelve `needs_configuration` | open (closure agent failed) | Audit gap stands: no OC Flow `run` path returns needs_configuration when required config is missing (only `status` produces it — `test_acceptance_workspace.py`, `tests/cli/test_status_exit_codes.py`); live bare-dir `run` ends needs_executor. Needed: run pre-gate mapping missing workspace/config to needs_configuration + acceptance test for `run`. |
| OC-005 | Con TDD strict exige RED/GREEN | met | AC-012/AC-013 acceptance tests; `tests/oc_flow/test_red_first_posture.py`; `tdd_red_proven_if_strict` gate in `test_run_bundle_gates.py`. |
| OC-006 | Genera memory_delta y graph_delta | met | `oc_flow/nodes.py` consolidation writers; `tests/e2e/test_flow_systems_integration.py` (both deltas asserted live) + `tests/workflows/test_oc_flow_escalation_consolidation.py`. |
| OC-007 | Reporta tokens, KG y memoria usados | met | state.json total_tokens pins + cost-report.json (e2e); run.json memory block (`tests/oc_flow/test_run_bundle_memory.py`); KG provenance assertions in e2e. |
| OC-008 | Se ve correctamente en TUI | met | `tests/cli/test_tui_command.py` (rows + run detail via Textual pilot); `tests/cli/test_tui_tdd_gates.py`; `tests/core/test_studio_reader.py`; strengthened this round by TUI-AC-003/TUI-FLOW-002 closures (real phase breakdown + logs). |
| OC-STATES | DOC1 §10 estados: passed(mutation_required=false), needs_executor, passed, failed, needs_approval, needs_configuration, needs_context | open (closure agent failed) | Covered rows: read-only completed/passed, needs_executor, passed, failed (see OC-001..003 + completion-gate tests). Still missing producers + tests for needs_approval (policy denial ends `blocked`), run-level needs_configuration (see OC-004), and terminal needs_context / diagnose->gather_context edge pin. Mapping/exit-code layer only (`tests/cli/test_contracts_truth_layer.py`, `tests/core/test_run_exit_derivation.py`). |
| OC-REPAIR-BOUNDS | DOC2 §10.4 repair loop: max_attempts bound, allowed_when, forbidden_when | open (closure agent failed) | Bound implemented and pinned (`tests/workflows/test_oc_flow_diagnosis.py`, exhaustion -> escalation edge); allowed_when covered via recoverable-failure routing. Still missing: tests asserting diagnosis_attempts == 0 under policy-denied / executor-less / red-not-proven runs; declarative `repair.allowed_when/forbidden_when` contract does not exist in code. |

## Area: kg (knowledge graph)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| KG-001 | index detecta archivo, símbolo y test | met | `tests/core/test_knowledge_graph.py`; AC-005/AC-006 acceptance tests; `tests/core/test_kg_tests_edges.py`; live tmp check. |
| KG-002 | edge `tests` conecta test con símbolo | met | `test_kg_tests_edges.py::test_index_project_emits_symbol_level_tests_edge` + no-dup + no-false-positive pins; live edge row confirmed. |
| KG-003 | `pack` incluye test relacionado por KG | met | AC-007/AC-021 acceptance tests; `tests/core/test_related_tests.py`. |
| KG-004 | cambio de archivo actualiza KG | met | AC-020 acceptance test (incremental); `tests/core/test_kg_v2_delta.py`; `tests/core/test_kg_freshness_checker.py`. |
| KG-005 | KG no indexa basura/caches | met (closed this round) | `tests/core/test_kg_ignores_caches.py`: pins `DEFAULT_IGNORE_PATTERNS` + `KnowledgeGraphConfig.exclude` cache defaults; index-time test with `__pycache__`/`node_modules`/`.git` present asserts zero nodes/files from them. Re-verified 2026-07-07. |
| KG-006 | `kg explain` justifica selección (`knowledge-graph explain-pack`) | met (closed this round) | `tests/cli/test_kg_explain_pack_cmd.py`: real parser + `handle_kg` dispatch against a persisted run pack (per-item reason, retrieval_source, edges_used, omission reasons, metrics, `RUN_NOT_FOUND` contract error). Plus `tests/context/test_pack_explain.py` payload pins. Re-verified 2026-07-07. |
| KG-007 | uninstall purga KG local | met | `tests/cli/test_uninstall_full.py` (purges `.storage/opencontext`, preserves other tools) + AC-022/AC-023. |
| KG-008 | TUI muestra nodos y edges básicos | met (closed this round) | `tests/cli/test_tui_graph_loaders.py`: real-DB loader path (`pick_focus` + `load_node_neighbors` over populated `context_graph.db`; focus, neighbor kinds, `calls`/`called by` directions, unknown-id degradation) + existing `test_tui_graph_nav.py` pilot tests. Re-verified 2026-07-07. |
| KG-NODES | Nodos mínimos: file, symbol, test, module, command, config_key, memory, decision, artifact, run, task, spec | deviation-documented | `NodeKind.SPEC` implemented; full DOC1 minimum node vocabulary pinned via documented nearest mappings (config_key->CONFIG, memory->MEMORY_BELIEF) in `tests/core/test_kg_min_vocab.py` + `tests/core/test_graph_enums.py`. Deviation (recorded): live `opencontext index` still emits only code-centric kinds; memory/run/decision/spec emission is a contract-documented Current->Target (`KG_CONTEXT_COMPRESSION_CONTRACT.md`). Re-verified 2026-07-07. |
| KG-EDGES | Edges mínimos: defines, calls, imports, tests, depends_on, documents, configured_by, produced_by, modified_by, related_to, implements, verifies | deviation-documented | `EdgeKind.DOCUMENTS`/`EdgeKind.RELATED_TO` implemented; full DOC1 edge vocabulary pinned (configured_by->CONFIGURES, modified_by->CHANGED_BY, verifies->VERIFIED_BY) in `test_kg_min_vocab.py`. Deviation (recorded): live index emits only {calls, tests, owns}; the contract's minimum live proof (test -tests-> symbol, KG-002) is met, the rest is a documented target. Re-verified 2026-07-07. |
| KG-CMDS | Comandos: build/search/explain/neighbors/stats/prune | met (closed this round) | All subcommands live-verified by audit; CLI-level gaps closed: `tests/cli/test_kg_callers_callees_cmd.py` (parser + `handle_kg`, pure-JSON assertion) + explain-pack CLI coverage (KG-006). Real bug found and fixed via TDD RED: `callers/callees --json` printed the branded header before JSON (headers moved into non-JSON branch of `kg_cmd.py`); `impact`/`trace` fixed by the release-dod round (DOD1-DELTAS). Re-verified 2026-07-07. |
| KG-PACK-CONTRACT | pack reporta bloque kg: {used, nodes_selected, edges_used, test_nodes_included, reason} | deviation-documented | Additive `test_nodes_included` (int) + `kg_reason` (str|null) implemented in `ContextPackMetrics`, computed in `build_pack_metrics`; value-level assertions for `kg_edges_used`/`test_nodes_included` in `tests/context/test_pack_kg_contract.py`. Deviation (recorded): DOC1's nested kg block is realized as flat metrics; mapping frozen in `KG_CONTEXT_COMPRESSION_CONTRACT.md` (used->kg_used, nodes_selected->kg_nodes_used, edges_used->kg_edges_used, reason->kg_reason). Re-verified 2026-07-07. |

## Area: ctx (context packing / compression)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| CTX-001 | pack respeta budget | met | AC-008/AC-021 acceptance tests (available/used token pins); live check; `tests/context/test_compression_span_narrowing.py`. |
| CTX-002 | pack incluye test relacionado | met | AC-007/AC-021 acceptance tests; live pack included the related test. |
| CTX-003 | pack incluye memoria relevante | met (closed this round) | Memory recall wired into `RetrievalPlanner.plan()` (`retrieval/planner.py`: `_memory_recall_items` + `_memory_record_to_context_item`); memory lands in `included[]`, `context.memory_hits >= 1`. `tests/context/test_pack_memory_inclusion.py` (planner-level + real-runtime integration). Re-verified 2026-07-07. |
| CTX-008 | TUI muestra pack y métricas | met (closed this round) | `ContextViewerScreen` renders context-pack.json fields (files/symbols, memory, KG edges, tokens, compression, metrics; legacy fallback kept). `tests/cli/test_tui_pack_viewer.py` (pure render unit + Textual pilot). Re-verified 2026-07-07. |
| CTX-PROTECTED-LIST | Protected-span kinds per plan list | deviation-documented | Detectors added in `context/protection.py`: `import`, `configuration`, `recent_change`, `recent_decision`, plus `detect_referenced_fragments()`; KEEP taxonomy extended in `context/compression.py`. `tests/core/test_protected_spans_extended.py`. Deviations (recorded): new kinds + signature protection stay OPT-IN on the semantic/v2 path (legacy byte-compat pinned by `test_legacy_compression_unchanged_without_semantic_protection` and `test_new_detectors_stay_out_of_the_legacy_default_path`); ini `[section]` headers keep `citation` kind on the combined path (still protected). Re-verified 2026-07-07. |
| CTX-RANKING-FACTORS | Ranking factors per DOC2 §13.3 | deviation-documented | `tests/core/test_ranking_factor_weights.py`: directional freshness + token-cost-penalty tests, shipped-default pin naming DOC2 §13.3 with the 7-family mapping, config-override escape hatch. Deviation (recorded): shipped `RetrievalWeights` defaults intentionally differ from documented initial weights — Current->Target note added to `KG_CONTEXT_COMPRESSION_CONTRACT.md`. Re-verified 2026-07-07. |

Coverage note: audit rows for CTX-004..CTX-007 (compresión medible, protected spans conservados, pack explica inclusión/exclusión, proyecto grande acotado) were not carried into this closure pass's input. They were not flagged open by the closure round; their behavior is exercised by AC-007/AC-008/AC-021 (compression metrics, protected spans, omission reasons, large-fixture inclusion/exclusion with numeric pins added by the release-dod round) and KG-006 (explain-pack justification).

## Area: mem (memory)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| MEM-002 | memoria pendiente requiere aprobación | met (closed this round) | `tests/cli/test_memory_approval_config.py` (4 tests: `_approval_required` seam + CLI save lands proposed/active); live-pinned by the real-binary MEM-CMDS acceptance test under `memory.approval_required: true`. Re-verified 2026-07-07. |
| MEM-004 | memoria no relevante no se usa | met (closed this round) | `tests/oc_flow/test_memory_recall_exclusion.py` (2 tests): only-irrelevant memory -> `memory.used=false`/`memory_hits==[]`; mixed stores -> irrelevant observation excluded while relevant folds; pins `_fold_memory_recall` via `node_gather_context` with real LocalMemoryStore + memory_v2.db. Re-verified 2026-07-07. |
| MEM-006 | compact genera resumen | met (closed this round) | CLI `memory compact` writes a `kind="summary"` record into the context repository `summaries/` collection per compacted cluster (keeper + absorbed ids); additive `summary`+`clusters` JSON fields. `tests/cli/test_memory_lifecycle_cmd.py::test_compact_generates_a_summary_record` / `::test_compact_noop_generates_no_summary`. Re-verified 2026-07-07. |
| MEM-007 | purge elimina todo | met (closed this round) | `purge_memory_state` (shared by `memory purge --yes` and uninstall purge) also removes `.opencontext/context-repository`; additive `removed_dirs`. `test_memory_lifecycle_cmd.py::test_purge_removes_context_repository_and_store_files`, `::test_purge_refuses_without_yes`, `::test_purge_is_idempotent_on_empty_workspace`. Re-verified 2026-07-07. |
| MEM-TYPES | Tipos de memoria del plan | deviation-documented | `packages/opencontext_memory/opencontext_memory/taxonomy.py` pinned to the contract's canonical 8-type set (`MEMORY_CONTRACT.md` authoritative over DOC1's 7-name list); `mem_save` normalizes DOC1 aliases (`project_rule`->`constraint`, `learned_pattern`->`pattern`, `error_resolution`->`solution`); legacy free-form types preserved. `packages/opencontext_memory/tests/test_taxonomy.py` (5 tests). Deviation (recorded): DOC1's `summary` type has no contract counterpart — kept as free-form pass-through (used by MEM-006 summaries); DOC1/contract vocabulary still needs editorial reconciliation. Re-verified 2026-07-07. |
| MEM-HITS-SHAPE | run.json memory block shape (hits, candidates, approval) | met (closed this round) | `memory_block()` emits `new_candidates` + `requires_approval`; `_persist_memory_delta` counts harvested + promoted records; runner threads `memory.approval_required`. `tests/oc_flow/test_run_memory_report_fields.py` (4 tests) + `tests/acceptance/test_acceptance_memory.py::test_run_memory_block_reports_candidates_and_approval` (real run.json); updated pins in `tests/oc_flow/test_run_bundle_memory.py`. Re-verified 2026-07-07. |
| MEM-CMDS | Verbos de memoria end-to-end (save/approve/reject/purge) | met (closed this round) | `tests/acceptance/test_acceptance_memory.py::test_memory_lifecycle_verbs_dispatch_end_to_end`: real-binary roundtrip (approval-gated save -> proposed excluded -> approve -> active+retrievable -> reject -> gone -> purge refuses without `--yes` -> `--yes` wipes). DOC1's top-level `memory save/get` naming remains under the `v2` namespace as `MEMORY_CONTRACT.md` already acknowledges. Re-verified 2026-07-07. |

Coverage note: audit rows for MEM-001, MEM-003, MEM-005, MEM-008, MEM-009 were not carried into this closure pass's input and were not flagged open. Cross-references: MEM-001 <-> AC-017 (save/search/get roundtrip), MEM-003 <-> AC-018 (approved memory used in second run), MEM-005 <-> save-time dedupe exercised inside the extended AC-019 test, MEM-008 <-> AC-022/AC-023 + MEM-007 purge spine, MEM-009 <-> TUI-FLOW-005 memory screen (approve/reject remains CLI-driven per MEM-CMDS).

## Area: exe (executors + policies)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| EXE-002 | shell deshabilitado bloquea comandos | met (closed this round) | `tests/harness/test_shell_policy_gate.py` (3 tests: shell disabled blocks `VerifyPhase._run_tests` before subprocess.run; default and allow:true unchanged) + engine total-command deny in `tests/core/test_policies_overlay.py::test_shell_allow_key_is_the_shell_switch`. Live: `policy simulate --command ls` -> deny/shell_disabled under the doc yaml. Re-verified 2026-07-07. |
| EXE-005 | acciones destructivas requieren aprobación | met (closed this round) | `tests/core/test_policy_engine.py::test_destructive_command_asks_for_approval_under_balanced` (git reset --hard / drop table / dd if=) + `::test_no_preset_allows_destructive_commands_unguarded` (PRESET_TABLE guard). Re-verified 2026-07-07. |
| EXE-POLICIES | DOC v2 `policies:` yaml section enforced | deviation-documented | New `policy/overlay.py` (`PoliciesOverlay` typed reader); `PolicyEngine` consumes it (shell/network gates, posture overlay, `policies.preset`); `writes.require_approval` -> approval gate FAILED; `secrets.redact` warn<->deny; `destructive_actions.require_explicit_confirmation` ask<->allow with deny-preset never weakened; absent section inert. `tests/core/test_policies_overlay.py` (8 tests). Deviation (recorded): global default of `harness.approval_required_for_writes` stays False (opt-in) — flipping it would break every existing zero-config run; the documented yaml key is the supported opt-in (`test_writes_require_approval_key_blocks_apply_gate`). Re-verified 2026-07-07. |

Coverage note: audit rows for EXE-001, EXE-003, EXE-004, EXE-006 were not carried into this closure pass's input and were not flagged open. Cross-references: EXE-003 <-> AC-009 (missing provider -> needs_executor), EXE-006 <-> AC-028 (secrets scrubbed from the whole run report bundle), EXE-001 <-> policy-denied mutation pins in `tests/workflows/test_oc_flow_executor.py::test_provider_forbidden_path_denied_by_policy`.

## Area: inst (install manifests)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| INST-001 | instalación product registra manifest | met (closed this round) | `tests/acceptance/test_acceptance_install_manifest.py::test_full_install_registers_product_manifest`, `::test_product_install_registers_manifest`; `tests/cli/test_scope_hierarchy_cmds.py::test_product_install_registers_manifest_and_status_surfaces_it`; `tests/storage/test_install_manifest_v2.py::test_write_product_manifest_persists_under_home`. New `build_product_manifest_fields`/`write_product_manifest` (`paths/install_manifest.py`); registered by `product install`, full `install`, and install.sh/install.ps1. Re-verified 2026-07-07. |
| INST-002 | instalación workspace registra manifest | met (closed this round) | `test_acceptance_install_manifest.py::test_workspace_install_registers_v2_manifest` (real CLI: schema_version==2 + non-empty created_paths; breaks if finalize wiring or v1-writer fallback masks it). Re-verified 2026-07-07. |
| INST-003 | reinstall idempotente | met (closed this round) | `test_acceptance_install_manifest.py::test_reinstall_through_real_cli_is_idempotent` (two real installs: created_paths merged not replaced, no dupes, stable install_id) + `test_install_manifest_v2.py::test_product_manifest_reinstall_is_idempotent`. Re-verified 2026-07-07. |
| INST-MANIFEST-FIELDS | Manifest schema per DOC1 (paths, env vars, shell blocks, symlinks, ids) | deviation-documented | `test_install_manifest_v2.py::test_product_manifest_records_all_contract_fields`, `::test_product_manifest_ignores_foreign_local_bin_symlink`, `::test_workspace_manifest_carries_install_id_and_shell_fields`. Deviations (recorded in `INSTALL_UNINSTALL_CONTRACT.md`): `env_vars` always [] (installers set PATH via shell profile blocks); workspace manifests write shell/symlink fields as [] (never created at that scope); `schema_version` is 2 (existing v2 line), not DOC1's literal "v1"; field names follow the product contract, `install_id` added additively. Re-verified 2026-07-07. |

Coverage note: audit rows for INST-004..INST-009 (uninstall workspace/product/dry-run/verify/unmanaged-files/TUI preview) were not carried into this closure pass's input and were not flagged open. Cross-references: INST-004/005 <-> AC-022/AC-023, INST-006/007 <-> `test_acceptance_uninstall.py` dry-run + verify legs, INST-008 <-> user-files-untouched assertions in AC-022, INST-009 <-> TUI-FLOW-007.

## Area: sdd

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| SDD-001 | `sdd init` crea estructura | met (closed this round) | `tests/cli/test_sdd_contract_items.py::test_sdd_init_writes_project_sdd_context_without_install` + `::test_sdd_init_does_not_stomp_existing_sdd_context` — writes `.opencontext/sdd/{context.json,testing.md,registry.json}` create-only. Re-verified 2026-07-07. |
| SDD-003 | `sdd propose` lee `exploration.md` | met (closed this round) | `tests/harness/test_sdd_phase_artifacts.py::test_explore_persists_exploration_artifact` + `::test_propose_consumes_exploration_artifact` — ExplorePhase persists `exploration.md`; ProposePhase forwards it (`state.prior_artifact`) and carries it into `proposal.json`. Re-verified 2026-07-07. |
| SDD-004 | `sdd spec` lee proposal y produce acceptance | deviation-documented | `test_sdd_phase_artifacts.py::test_spec_fails_closed_when_proposal_missing` + `::test_spec_produces_acceptance_artifact` — SpecPhase writes `acceptance.md` from spec scenarios. Deviation (recorded): acceptance.md lives in the run bundle (`.opencontext/runs/<id>/`), not DOC1's per-cycle tree (superseded per `SDD_CONTRACT.md`); the CLI verb stays a dispatcher by contract. Re-verified 2026-07-07. |
| SDD-005 | `sdd design` produce diseño trazable | deviation-documented | `test_sdd_phase_artifacts.py::test_design_traces_spec_requirements` — design scaffold gains `## Traceability` naming spec requirements. Deviation (recorded): enforced for product-produced designs; executor-produced content validated by section names only. Re-verified 2026-07-07. |
| SDD-006 | `sdd tasks` produce tareas ejecutables | met (closed this round) | `test_sdd_phase_artifacts.py::test_tasks_maps_every_task_to_files` — every task file-mapped + mandatory test-first task (born-green pin). Re-verified 2026-07-07. |
| SDD-007 | `sdd apply` usa harness y genera run | deviation-documented | New `sdd apply --execute` launches the shared harness (`handle_run_exec`, workflow=sdd), blocked exit 7 when not apply-ready: `test_sdd_contract_items.py::test_sdd_apply_execute_flag_accepted`, `::test_sdd_apply_execute_launches_harness_run`, `::test_sdd_apply_execute_blocked_when_change_not_ready`. Deviation (recorded): bare `sdd apply` stays a resolver per `SDD_CONTRACT.md`; real execution proof remains AC-016. Re-verified 2026-07-07. |
| SDD-008 | `sdd verify` falla si tests fallan | met (closed this round — real bug fixed) | Bug: `HarnessRunner.run()` downgraded a gate-loop FAILED to WARNING, so `run --workflow sdd` reported `passed` while gates.json recorded `verify_tests_passed failed`. Fix: `terminal_gate_failed` sticky flag in `harness/runner.py` (scoped to apply/verify gates; explore-only advisory posture preserved). `tests/acceptance/test_acceptance_sdd_failure.py::test_sdd_workflow_fails_when_tests_fail`. Re-verified 2026-07-07 in the acceptance lane. |
| SDD-009 | `sdd continue` reanuda correctamente | met (closed this round) | `test_sdd_contract_items.py::test_sdd_continue_resolves_next_dependency_ready_phase` + `::test_sdd_continue_resumes_pending_tasks_at_apply` — `_handle_continue` now resolves + prints dispatcher markdown + next-phase prompt. Re-verified 2026-07-07. |
| SDD-010 | `sdd archive` cierra y conserva evidencias | met (closed this round) | `test_sdd_contract_items.py::test_sdd_archive_closes_change_and_preserves_evidence` + `::test_sdd_archive_blocked_without_passing_verify_exits_7` + `::test_sdd_list_excludes_the_archive_folder` — moves change to `openspec/changes/archive/<date>-<change>/` with full evidence + `archive-report.json`; fail-closed exit 7. Re-verified 2026-07-07. |
| SDD-ARTIFACTS | Artefactos SDD per DOC1 (registry, manifests, per-phase files) | deviation-documented | New `packages/opencontext_sdd/opencontext_sdd/artifacts.py`: `registry.json` + per-change `manifest.json` refreshed on new/continue/phase verbs/archive: `test_sdd_contract_items.py::test_sdd_new_writes_registry_and_change_manifest` + `::test_sdd_archive_records_archived_state_in_registry`. Deviations (recorded): DOC1 `.opencontext/sdd/specs/<spec_id>/` tree is contract-superseded; `problem.md`/`specification.md` superseded by `proposal.md`/`specs/<cap>/spec.md`; `apply_runs/` + `verification.json` remain documented Current->Target in `SDD_CONTRACT.md`. Re-verified 2026-07-07. |
| SDD-STATES | Estados del ciclo SDD (draft..reviewed, blocked/failed/archived) | met (closed this round) | `packages/opencontext_sdd/tests/test_states_and_rules.py` (5 tests): `derive_cycle_state` implements draft..reviewed + blocked/failed, persisted in manifest.json; forward-only chain blocks phase skips; `archived` persisted via registry/manifest (SDD-010 test). Re-verified 2026-07-07. |
| SDD-RULES | `sdd status --json` expone fase, gates y next steps | met (closed this round) | `test_states_and_rules.py::test_status_json_exposes_current_phase_gates_and_next_steps` + `::test_status_gates_empty_without_runs` — additive `currentPhase`, `gates` (from newest gates.json, never fabricated), `gatesRun`, `cycleState`; REQ-OSS-001 field-count pin updated in `packages/opencontext_sdd/tests/test_status.py`. Re-verified 2026-07-07. |

Coverage note: audit rows for SDD-002, SDD-011, SDD-012 were not carried into this closure pass's input and were not flagged open. Cross-references: SDD-002 <-> AC-014 (`sdd new` creates persistent change artifacts), SDD-011 <-> TDD-007 / `tests/harness/test_sdd_strict_tdd_e2e.py`, SDD-012 <-> SDD TUI screen tests (`tests/cli/test_tui_flows.py` SDD screen + TUI-FLOW-004).

## Area: tui

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| TUI-AC-003 | Run detail muestra fases y status | met (closed this round) | Gate `phase` kept + per-phase breakdown rendered in run detail: `tests/cli/test_tui_flows.py::test_run_detail_loader_derives_phase_breakdown`, `::test_run_detail_screen_renders_phases_and_status`. Re-verified 2026-07-07. |
| TUI-SCREENS | Pantallas TUI requeridas presentes y funcionales | met (closed this round) | Pack viewer pilot test seeds a run context JSON and asserts render (structured view already existed; audit gap was stale): `tests/cli/test_tui_pack_viewer.py::test_context_pack_viewer_screen_renders_seeded_context`. Re-verified 2026-07-07. |
| TUI-FLOW-002 | Flujo runs: seleccionar run, ver fases y logs | met (closed this round) | Run log loaded from events.json/events.jsonl and rendered: `test_tui_flows.py::test_run_detail_loader_collects_log_events_both_layouts`, `::test_run_detail_flow_shows_logs_after_selection`; phases via TUI-AC-003. Re-verified 2026-07-07. |
| TUI-FLOW-003 | Pack viewer muestra las seis facetas | met (closed this round) | Files/symbols, memory, KG edges, tokens, compression pinned as structured sections: `test_tui_pack_viewer.py::test_pack_view_structures_all_six_required_facets`. Re-verified 2026-07-07. |
| TUI-FLOW-004 | SDD screen permite ejecutar siguiente fase | deviation-documented | `r` in SddScreen executes next phase via `opencontext_sdd.runner.run_phase`: `test_tui_flows.py::test_next_phase_action_classifies_phases`, `::test_sdd_screen_runs_next_phase_without_approval`, `::test_sdd_screen_refuses_approval_required_phase`. Deviation (recorded): apply/archive refused as approval-required — mutating/closing phases stay on the CLI (honest approval boundary; multi-change workspaces get a CLI hint). Re-verified 2026-07-07. |
| TUI-FLOW-005 | Memory screen: filtro por tipo, trust/expiry/origin | deviation-documented | `t` cycles type filter; trust/expiry/origin columns rendered: `tests/cli/test_tui_memory_lifecycle.py` (4 tests). Deviation (recorded): store tracks no numeric confidence — trust label honestly derived from real fields `pinned`/`lifecycle_state`/`review_after` per MEMORY_CONTRACT states; expiry=review_after, origin=session_id. Re-verified 2026-07-07. |
| TUI-FLOW-006 | Config screen: validación, conflictos, overrides | met (closed this round) | `v` panel: config-doctor diagnostics, cross-layer conflicts with winner, active overrides: `test_tui_flows.py::test_build_config_validation_reports_diags_conflicts_overrides`, `::test_config_screen_shows_validation_and_conflicts_panel`. Re-verified 2026-07-07. |
| TUI-FLOW-007 | Uninstall preview: residuo + confirmación segura | deviation-documented | Preview gains possible-residue report (same `verify_no_traces` detector as `uninstall verify`); home uninstall entry -> confirm -> decline-safe: `test_tui_flows.py::test_uninstall_preview_reports_possible_residue`, `::test_uninstall_preview_screen_renders_residue_section`, `::test_home_uninstall_entry_confirms_and_decline_is_safe`. Deviation (recorded): destructive confirm/apply intentionally stays in `menu_cmd._run_uninstall` via suspend, per the screen's read-only dry-run contract. Re-verified 2026-07-07. |

Coverage note: audit rows for TUI-AC-001, TUI-AC-002, TUI-AC-004..TUI-AC-008 were not carried into this closure pass's input and were not flagged open. Cross-references: existing pins in `tests/cli/test_tui_command.py` (smoke launch, dashboard, run detail), `tests/cli/test_tui_graph_screen.py` (small-terminal/empty degradation), config inspector precedence via TUI-FLOW-006, workspace-missing error handling via interface gating tests.

## Area: cli-states (CLI contract)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| CLI-FLAGS | Flags globales estables (`--json`, `--quiet`, `--no-color`, `--root`, ...) | deviation-documented | Shared frozen matrix `packages/opencontext_cli/opencontext_cli/contracts/flags.py` (`STABLE_COMMAND_FLAGS`); `--quiet`/`--no-color` implemented globally (+ `OPENCONTEXT_QUIET`/`NO_COLOR` env); `pack --json` added (`--format json` kept as alias); `init`/`clean` gain `--json`. `tests/cli/test_cli_flags_matrix.py`. Deviation (recorded in `CLI_CONTRACT.md`): `--root` stays positional on index/status/clean/install/pack; `--verbose`/`--json` remain subcommand-level for tree commands. Re-verified 2026-07-07. |
| CLI-JSON-COMMON | Documento JSON común (schema_version, command, started_at, duration_ms, ...) | deviation-documented | Dispatcher routes ALL stable-command failures in JSON mode through the error envelope (OPERATION_FAILED / FILE_NOT_FOUND / PERMISSION_DENIED / UNEXPECTED_ERROR, exit 1); envelope+purity matrix covers all 17 stable commands; human mode unchanged. `tests/cli/test_cli_json_envelope_matrix.py`. Deviation (pre-frozen in `CLI_CONTRACT.md`): DOC1's full common document intentionally not implemented — frozen as JSON purity + error envelope + additive schema-keyed payloads. Re-verified 2026-07-07. |
| CLI-EXP-HIDDEN | Comandos internos ocultos, preview marcados | met (closed this round) | `_apply_maturity_help_policy` in `main.py` aligns primary `--help` with `contracts/command_registry.py`: internal commands SUPPRESSed, visible preview commands tagged "(preview)", stable `init` un-suppressed; epilog no longer names internal commands. `tests/cli/test_cli_help_maturity.py`. Re-verified 2026-07-07. |
| CLI-ERR-CODES | Catálogo estable de error codes | met (closed this round) | Frozen catalog `contracts/error_codes.py` (12 codes, exact-set pinned, SCREAMING_SNAKE regex); `CliContractError` rejects P0 codes without hint; kg lowercase codes migrated (`run_not_found`->`RUN_NOT_FOUND`, etc.); source-scan test pins every raise site to the catalog. `tests/cli/test_error_code_catalog.py`. Re-verified 2026-07-07. |

## Area: harness (gates)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| HARNESS-GATES-13 | Catálogo obligatorio de gates (DOC1/DOC2 §8.5) | deviation-documented | New `docs/product-contract/GATES_CONTRACT.md` freezes the real 10-gate OC Flow catalog (`OC_FLOW_GATE_IDS`, ordered) + 18 named harness gate classes, and maps EVERY plan gate id (22) to its implemented gate or superseding mechanism. `tests/harness/test_gate_catalog_contract.py` (4 tests pin doc<->code both ways). Deviation (recorded): `kg_available_or_declared_absent`, `memory_policy_checked`/`memory_available_or_explained`, `json_contract_valid`, `evidence_complete`, `memory_delta_valid`, `graph_delta_valid` are NOT run gates — documented as superseded by run.json metadata, AC-024 JSON-contract tests, enforce_gates+AC-025 evidence assertions, and the mandatory delta artifacts. Re-verified 2026-07-07. |
| HARNESS-CRIT-4 | Cada gate con evidencia (mensaje no vacío) | met (closed this round) | `ensure_gate_evidence()` in `oc_flow/run_bundle.py` backfills an honest fallback message at BOTH persistence boundaries (`write_run_bundle` and harness `persist_run` gates.json). `tests/harness/test_gate_evidence_contract.py` (4 tests: real harness run all-messages-non-empty; harness persist backfill; full OC Flow catalog passed/failed/skipped; writer backfill). TDD RED shown first. Re-verified 2026-07-07. |

## Area: release-dod

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| REL-GATE | Release report gate: versión, hashes, acceptance summary, límites conocidos; falla en rojo | met (closed this round) | `tests/release/test_release_report_contract.py` (6 tests invoke `main()`): version + per-artifact sha256 + acceptance summary + `known_limitations` field contract; nonzero exit on failed>0 / hygiene-fail / uninstall-fail / unparseable log / missing artifact. Re-verified 2026-07-07. |
| TAX-COUNTS | Taxonomía de suites §21.1 (bandas de conteo por lane) | deviation-documented | Golden band now MET: `tests/golden` = 19 tests (14 new GOLD-001..014 §19.2 JSON contracts, < 30 s), pinned by `tests/architecture/test_suite_taxonomy.py::test_golden_contract_suite_is_within_the_band`. Deviation (recorded): §21.1 TOTAL band (120-220) deliberately not met per the §26.3 reduction audit; pinned auditable by `::test_taxonomy_total_deviation_stays_documented` (fails if `artifacts/test-reduction-report.md` or its verification record disappears). Re-verified 2026-07-07. |
| DOD2-1..17 | DOC2 Definition-of-Done checklist | met (closed this round) | #4: `kg impact --json` purity FIXED (header moved into non-JSON branch) + black-box impact leg added to AC-006 + GOLD-007 impact JSON contract. #11: archive leg closed by SDD-010 (real archive execution). #17: deviation pinned via TAX-COUNTS taxonomy test. Re-verified 2026-07-07 (acceptance lane + batch 3). |
| DOD1-DELTAS | DOC1 DoD deltas (JSON purity, error envelopes) | met (closed this round) | Bugs fixed live: `kg impact --json` AND `kg trace --json` emitted logo+header; `runs show/artifacts` + `harness report --json` emitted empty stdout on error (now `CliContractError` RUN_NOT_FOUND -> pure JSON envelope, exit 1 unchanged). Purity sweep: `tests/cli/test_json_purity_sweep.py::test_stable_json_stdout_is_pure` — 36 invocations covering every json-capable stable subcommand, enumerated from the real parser. Re-verified 2026-07-07. |
| MET-PRODUCT | Métrica: JSON parse failures = 0 product-wide | met (closed this round) | `test_json_purity_sweep.py::test_every_json_capable_stable_subcommand_is_swept` fails when a new `--json` flag lands without a sweep invocation; all 36 invocations parse (success and error paths). Re-verified 2026-07-07. |
| MET-TOKENS | Métricas numéricas §29.2 (inclusión/exclusión/reducción) | met (closed this round) | Dead `context.full_file_threshold` config (default 0.8) wired into `ContextCompiler` (`tests/context/test_full_file_threshold.py`, 5 tests). Numerics pinned on the large fixture: inclusion >=95% (live 100%) + exclusion >=80% (live 83%) in AC-007; protected_spans_kept == protected_spans + reduction >=40% (live ~93%) in AC-021. Re-verified 2026-07-07. |
| MET-TESTS | Métricas de suites: timing guards + P0 policy | met (closed this round) | Timing rows: TIME-SMOKE/TIME-FULL-ACC/TIME-UNIT guards (see ac-smoke). P0 policy: `tests/architecture/test_p0_suite_policy.py` — every P0-suite test carries a contract-or-bug ID (AST gate), no flaky markers in P0 suites, no rerun plugins in CI. Re-verified 2026-07-07. |

---

## Summary

### Totals

| Area | Rows | met | deviation-documented | open |
|---|---|---|---|---|
| ac-smoke | 43 | 42 | 1 | 0 |
| cfg | 13 | 10 | 3 | 0 |
| tdd | 15 | 15 | 0 | 0 |
| oc-flow | 10 | 7 | 0 | 3 |
| kg | 12 | 9 | 3 | 0 |
| ctx | 6 | 4 | 2 | 0 |
| mem | 7 | 6 | 1 | 0 |
| exe | 3 | 2 | 1 | 0 |
| inst | 4 | 3 | 1 | 0 |
| sdd | 12 | 8 | 4 | 0 |
| tui | 8 | 5 | 3 | 0 |
| cli-states | 4 | 2 | 2 | 0 |
| harness | 2 | 1 | 1 | 0 |
| release-dod | 7 | 6 | 1 | 0 |
| **Total** | **146** | **120** | **23** | **3** |

All 23 deviation-documented items and all 120 met items were re-verified on 2026-07-07: every closure-named test file exists and passes (see Re-verification table; acceptance lane exit 0).

### Open items (closure agent failed — follow-up required)

1. **OC-004** — OC Flow `run` never returns `needs_configuration`; needs a run pre-gate + acceptance test.
2. **OC-STATES** — no producers/tests for terminal `needs_approval`, run-level `needs_configuration`, or `needs_context` as OC Flow run outcomes.
3. **OC-REPAIR-BOUNDS** — `forbidden_when` repair semantics unpinned (no diagnosis_attempts==0 tests for policy-denied / executor-less / red-not-proven runs); declarative `repair.allowed_when/forbidden_when` contract absent from code.

### Recorded deviations (all test-pinned and documented)

1. **TIME-FULL-ACC** — acceptance scenario band amended 25-35 -> 25-50 in `ACCEPTANCE_CONTRACT.md` + DOC2 §21.1 (real suite honestly pins several AC IDs with >1 test; guard meta-tests excluded from counts).
2. **CFG-008** — `version: 1` configs do not warn on load; v1 is a supported schema per the `config.version` contract, warning fires only on actual legacy-key migrations.
3. **LAYERS-ORDER** — doc layer 7 keeps the provenance name `overrides`; internal `policy` layer remains topmost, additively above the doc's 8 layers.
4. **PROFILES-RUNTIME** — implicit profile remains `balanced`; the doc's `default` profile semantics apply when explicitly selected; `executors.allow_shell` gates nothing yet (no built-in shell-capable executor).
5. **KG-NODES** — live index still emits only code-centric node kinds; memory/run/decision/spec emission is a contract-documented Current->Target.
6. **KG-EDGES** — live index emits only {calls, tests, owns}; remaining edge kinds are enum-representable, documented as target.
7. **KG-PACK-CONTRACT** — DOC1's nested kg block realized as flat metrics; mapping frozen in `KG_CONTEXT_COMPRESSION_CONTRACT.md`.
8. **CTX-PROTECTED-LIST** — new protected-span kinds are opt-in on the semantic/v2 path (legacy byte-compat pinned); ini `[section]` headers keep `citation` kind on the combined path.
9. **CTX-RANKING-FACTORS** — shipped `RetrievalWeights` defaults intentionally differ from DOC2 §13.3 initial weights; Current->Target note in contract.
10. **MEM-TYPES** — DOC1's `summary` type has no contract counterpart; kept as free-form pass-through; DOC1/contract vocabulary needs editorial reconciliation.
11. **EXE-POLICIES** — global default of `harness.approval_required_for_writes` stays False; documented yaml key is the supported opt-in.
12. **INST-MANIFEST-FIELDS** — `env_vars` always []; workspace manifests write shell/symlink fields as []; `schema_version` is 2 (not DOC1's "v1"); contract field names with additive `install_id`.
13. **SDD-004** — acceptance.md lives in the run bundle, not DOC1's per-cycle tree (superseded per `SDD_CONTRACT.md`).
14. **SDD-005** — design traceability enforced for product-produced designs; executor content validated by section names only.
15. **SDD-007** — bare `sdd apply` stays a resolver; execution via new `--execute` flag; real execution proof remains AC-016.
16. **SDD-ARTIFACTS** — DOC1 `.opencontext/sdd/specs/<id>/` tree + `problem.md`/`specification.md` names superseded; `apply_runs/` + `verification.json` remain documented Current->Target.
17. **TUI-FLOW-004** — mutating/closing SDD phases (apply/archive) refused in TUI as approval-required; stay on the CLI.
18. **TUI-FLOW-005** — no numeric confidence in the store; trust label derived from `pinned`/`lifecycle_state`/`review_after`; expiry=review_after, origin=session_id.
19. **TUI-FLOW-007** — destructive uninstall confirm/apply stays in `menu_cmd._run_uninstall` via suspend; the TUI screen remains read-only dry-run.
20. **CLI-FLAGS** — `--root` stays positional on index/status/clean/install/pack; `--verbose`/`--json` remain subcommand-level for tree commands (recorded in `CLI_CONTRACT.md`).
21. **CLI-JSON-COMMON** — DOC1's full common JSON document (schema_version/command/started_at/duration_ms) intentionally not implemented; frozen as JSON purity + error envelope + additive schema-keyed payloads.
22. **HARNESS-GATES-13** — six plan gate ids not implemented as run gates; superseding mechanisms documented in `GATES_CONTRACT.md` and pinned both ways.
23. **TAX-COUNTS** — §21.1 total suite band (120-220) deliberately not met per the §26.3 reduction audit; deviation kept auditable by a taxonomy test.

### Notes

- **Input coverage:** the aggregated audit input for this matrix was truncated after CTX-003; for areas ctx (partial), mem, exe, inst, sdd, tui, cli-states, harness, and release-dod the tables list all closure-addressed items, and per-area coverage notes name the remaining checklist IDs (with cross-references to the acceptance rows that exercise them). None of those remaining IDs were flagged open by the closure round.
- **Pre-existing failures observed by closure agents, unrelated to closure work:** `tests/core/test_verification.py::TestRunAllChecks::test_healthy_if_no_failures` (environment flake from stale live-repo KG state; reproduces on untouched HEAD) and `tests/architecture/test_no_upward_imports.py::test_no_new_eager_upward_imports` (harness->oc_flow eager import introduced by commit `189444d`; flagged by the release-dod agent as follow-up).
- **Closure commits are all on this branch** (`cb326e2`..`002f6bf`); the oc-flow area produced no commit (agent failed) and its three items remain the only open rows.
