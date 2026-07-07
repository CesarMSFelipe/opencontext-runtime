# Product Contracts

Canonical, executable contracts that define what "OpenContext works" means. The acceptance
harness (`ACCEPTANCE_CONTRACT.md`) is the enforcement mechanism; every other contract points
at the test IDs that verify it. Where the current implementation differs from the target, the
contract carries an explicit "Current → Target" note.

| Contract | One line |
|---|---|
| [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md) | What OpenContext is, command maturity tiers, stable commands, mandatory flows, Definition of Done. |
| [CLI_CONTRACT.md](CLI_CONTRACT.md) | Global flags, JSON purity, standard error envelope, exit codes, semver promise. |
| [RUN_STATE_CONTRACT.md](RUN_STATE_CONTRACT.md) | The only canonical final states, their exit-code mapping, and the no-evidence-no-passed rule. |
| [GATES_CONTRACT.md](GATES_CONTRACT.md) | The mandatory gate catalog per workflow, enforcement rules, and the per-gate evidence rule. |
| [ACCEPTANCE_CONTRACT.md](ACCEPTANCE_CONTRACT.md) | AC-001..AC-030 and SMOKE-001..010 black-box scenarios, execution modes, timing budgets. |
| [INSTALL_UNINSTALL_CONTRACT.md](INSTALL_UNINSTALL_CONTRACT.md) | Product/workspace/agents scopes, manifest schemas, manifest-driven uninstall algorithm, safety rules. |
| [TDD_STRICT_CONTRACT.md](TDD_STRICT_CONTRACT.md) | RED → GREEN contract, evidence JSON shapes, and strict-mode policies. |
| [SDD_CONTRACT.md](SDD_CONTRACT.md) | SDD command surface, real artifact layout, state machine, phase-dependency rules. |
| [MEMORY_CONTRACT.md](MEMORY_CONTRACT.md) | Memory types, lifecycle states, usage-evidence rules, command surface. |
| [KG_CONTEXT_COMPRESSION_CONTRACT.md](KG_CONTEXT_COMPRESSION_CONTRACT.md) | KG node/edge minimums, query surface, pack pipeline, protected spans, mandatory pack metrics. |
| [RELEASE_CONTRACT.md](RELEASE_CONTRACT.md) | Release gate pipeline, artifact hygiene forbidden list, release report contents. |

Source plans: `docs/opencontext_plan_funcional_cierre_y_tests_reales.md` and
`docs/opencontext_plan_cierre_completo_sdd_tui_config_tests.md`.
