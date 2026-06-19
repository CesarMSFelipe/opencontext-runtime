# OpenContext Runtime — Systems Review (Round 4)

Date: 2026-06-20. Method: fix-and-verify pass over every Round-2/3 finding —
each fix implemented against source, covered by a behavioral regression test,
and validated by the full suite (**1761 passed, 6 skipped, 0 failed; ruff
clean**). Supersedes Rounds 1–3 (their text remains in git history).

## Thesis

Round 2 found a deep tier of seam failures: cross-process severance, final-order
loss, "validate-but-never-enforce", and config-literal drift. Round 3 closed
every in-process CRITICAL/HIGH. **Round 4 closes the two remaining architectural
CRITICALs (C3/C4) and the deferred MEDIUM/LOW items** — the two-process flagship
loops now actually work in-process, the apply phase writes real code, and the
LOW dead-code/UX items are fixed or honestly retired.

Per-subsystem scores (Round 2 → now): harness 4 → 8, memory 4 → 7, KG/context
4 → 7.5, LLM/MCP 3.5 → 7.5, config/setup 4.5 → 7.5, CLI/plugins 5.5 → 7.5.
**Integration-spine overall ≈ 4.5 → 7.5/10.** The seams are connected and
load-bearing; what remains is the absorb-list (real embeddings, plugin OS
sandbox) and genuine feature depth, not broken wiring.

---

## CLOSED — CRITICAL (all four)

- **C1 — MCP launch command** `["serve","--mcp"]`→`["mcp"]`; emitted args are
  tested against the live CLI argparser.
- **C2 — Memory split-brain** — the harness now resolves its agent store from the
  project config at `.storage/opencontext` (the recall path), so harvest and
  recall share one DB.
- **C3 — Host-model sampling now reachable in-process.** The flaw was purely the
  two-process split (sampler in the `mcp` process, loop in the `loop` process).
  Added the **`opencontext_run` MCP tool**: its handler drives the harness in the
  MCP server process, where the host sampler was registered during `initialize`.
  The runner's `_resolve_gateway` already prefers that sampler, so spec/design/
  tasks and apply codegen use the host's selected model with zero provider config.
  Transport is also hardened: timeout (M7), redaction (M8), content envelope (H6).
- **C4 — Standalone loop now writes code.** When a real executor is wired (host
  sampler / provider), the runner asks the model (builder persona) for concrete
  file edits as a JSON `[{path,content}]` array, parses them defensively, and
  feeds them to ApplyPhase — which enforces forbidden_paths and rolls back on
  error. No parseable edits ⇒ apply stays honestly planned, and the loop reports
  which case occurred (read from the apply manifest).

## CLOSED — HIGH (all seven)

H1 hybrid score persisted + compiler order preserved (redundant ranker removed).
H2 failure-memory boost map fed into ranking. H3 plugin.json unified +
entry_checksum stamped on install (load() verifies). H4 menu uninstall →
Configurator.deconfigure (no whole-file unlink). H5 (all four parts): 5 dropped
gates bound; forbidden_paths enforced in the edit executor; token-ledger status
via the enforcer; GGA scans the apply manifest's written source. H6 MCP
content-envelope + ping + notifications handling. H7 unknown provider degrades to
mock+warn (was a hard crash).

## CLOSED — MEDIUM (all nine)

M1 compression-to-fit now applies to any priority (was P0/P1 only, so it almost
never fired). M2 post-run reindex finalizes cross-file edges. M3 memory recalled
into the pack prompt; dead scaffolding deleted. M4 cross-store memory-id message.
M5 markdown jaccard dedup. M6 prefs→yaml bridge (menu + onboarding). M7 sampling
timeout. M8 secret redaction at the MCP/sampling boundary. M9 `.gitignore`
storage block written by the shared OnboardingService.

## CLOSED — LOW

- `pack .` now auto-indexes a fresh checkout (was excluded → empty pack).
- `opencontext_context` honors an explicit `max_nodes` (the `==20` sentinel no
  longer overrides an explicit 20).
- The backup-cleanup days prompt routes through `prompts.py` (was a stray
  `IntPrompt.ask`).
- Per-phase model routing: `models.phases` overrides now reach the executor via
  `_phase_model_map`; the dead `current_phase_model` field and `_model_for_phase`
  removed.
- Removed the not-implemented `AgentInstaller.uninstall` stub (real path is
  `Configurator.deconfigure`).

---

## REMAINING — absorb-list and intentional keeps (not bugs)

- **Real local embeddings** — `DeterministicEmbeddingGenerator` is SHA256-seeded
  random vectors; semantic vector search is a no-op even when enabled. A real
  sentence-transformer/GGUF backend is the upgrade (absorb-list).
- **Plugin OS-process sandbox** — `is_allowed`/checksum are declared, stamped on
  install, and verified at load, but in-process `exec` still grants full
  privilege. True capability enforcement needs a subprocess jail / capability
  broker (absorb-list).
- **Provider adapter depth** — `max_retries` is declared but no retry/backoff is
  implemented, and there is no streaming. Real provider-client work, deferred.
- **Intentional keeps** (not dead): `SDDOrchestrator` is retained for its
  `PHASE_DEPENDENCIES`/`WORKFLOW_TRACKS` DAG declaration consumed by the runner;
  `InstallationManager.install` is live (CLI + tested); `EngramMemoryAdapter`/
  `MemoryDelta` remain a supported public surface; `store_by_topic_key` + its
  columns are kept (removal is a schema migration with low payoff). The
  `Configurator` `scope`/`location` arg is cosmetic by design (paths come from the
  per-agent adapter) and documented as such.

---

## Verification
Full suite: **1761 passed, 6 skipped, 0 failed**; ruff clean. Every closed
finding has a behavioral regression test that fails if the fix is reverted.
Commits are small and single-concern (one finding per commit, tests alongside,
no co-author line per project convention).
