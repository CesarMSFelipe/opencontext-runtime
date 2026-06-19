# OpenContext Runtime — Systems Review (Round 3)

Date: 2026-06-19. Method: fix-and-verify pass over every Round-2 finding —
each fix implemented against source, covered by a behavioral regression test,
and validated by the full suite (1753 passed, 6 skipped, 0 failed; ruff clean).
Supersedes Round 2 (Round-1 and Round-2 text remain in git history).

## Thesis

Round 2 found a deep tier of **seam failures** — cross-process severance,
final-ordering loss, "validate-but-never-enforce", and config-literal drift.

Round 3: **every Round-2 CRITICAL and HIGH that was an in-process bug is now
closed and tested.** The two genuinely *architectural* items (the standalone
`mcp` ↔ `loop` two-process split, C3/C4) are addressed where they were
*dishonest* (silent degradation, invalid launch command, write-only memory) and
their remaining structural completion is scoped precisely below rather than
faked. The "enforce never" pattern is reversed: gates, forbidden-paths, secret
redaction, and plugin integrity now run at real call sites.

Per-subsystem scores (was → now): harness 4 → 7, memory 4 → 7, KG/context 4 → 7,
LLM/MCP 3.5 → 6.5, config/setup 4.5 → 7.5, CLI/plugins 5.5 → 7.
**Integration-spine overall ≈ 4.5 → 7/10** — the spine is connected; what
remains is the two-process feature work and minor cleanups, not broken seams.

---

## CLOSED in Round 3 (verified: fix + regression test)

### Tier 0 — advertised-but-broken (were CRITICAL/HIGH)
- **C1 — MCP launch command** (`configurator/constants.py`): `["serve","--mcp"]`
  → `["mcp"]`. The CLI has no `serve` subcommand; every configured agent got a
  command that exits with argparse error. Test asserts the emitted args parse
  against the live CLI argparser (`tests/configurator/test_mcp_shapes.py`).
- **C2 — Memory split-brain** (`harness/runner.py`): the harvester wrote to
  `<root>/.opencontext/memory.db` (provider hardcoded local) while recall reads
  `<root>/.storage/opencontext` honoring `memory.provider`. The harness now
  resolves its store from the project config at the runtime's path, so harvest
  and recall share one DB. Test writes via the harness store and reads it back
  through a fresh store at the recall path.
- **H4 — Menu uninstall data loss** (`menu_cmd.py`): routed through
  `InstallationManager().uninstall()`, which `unlink()`s the whole CLAUDE.md and
  mcp.json. Now routed through `Configurator.deconfigure` (surgical managed-block
  strip), matching the CLI `uninstall`.
- **H7 — Gemini/Mistral install crash** (`runtime.py`): an unknown detected
  provider raised `ConfigurationError` on every `OpenContextRuntime()`
  construction. Now degrades to the mock gateway with a loud warning.

### Tier 1 — headline capability
- **H1 — Hybrid ranking discarded** (`retrieval/planner.py`,
  `context/compiler.py`): the planner computed `compute_hybrid_score` only as a
  sort key and never wrote it back; the compiler then re-ranked with a weaker
  `ContextRanker`. Now the hybrid score is persisted onto each item and the
  compiler preserves planner order (the redundant ranker is removed). Graph/PPR/
  memory/freshness signals are live on every pack.
- **H2 — Memory boost map always empty** (`retrieval/planner.py`): `plan()` now
  builds a failure-memory boost map (FAILURE-layer `linked_nodes` keyed to
  candidate ids) and feeds it into `rank()`. Test proves a flagged candidate
  outranks an otherwise-identical one.
- **M3 — Memory never re-enters prompts** (`runtime.py`): wired
  `ProgressiveDisclosureMemory.select` into the context-pack prompt via the
  assembler's `memory` slot. Deleted the zero-caller `context_dag` /
  `temporal_memory` scaffolding and the scaffold-only `memory facts/timeline/
  supersede` CLI commands.
- **H6 — MCP envelope/handshake** (`mcp_stdio.py`): `tools/call` results now use
  the spec content envelope (`content[]` + `isError`, structured payload under
  `structuredContent`); dropped the non-standard `server/initialized`; ignore
  notifications (no reply to `notifications/initialized`); added `ping`.

### Tier 2 — enforcement & symmetry
- **H5 — Gates/guardrails declared but not dispatched** (`harness/`): bound the
  five silently-dropped gates (`no_secret_leakage`, `trace_id_created`,
  `included_sources_present`, `omissions_recorded`, `review_artifact_created`)
  to state-derived inputs; enforce `forbidden_paths` in the edit executor before
  any write (zero mutation on violation); compute the phase token-ledger status
  via the enforcer (the budget gate was a no-op); GGA now scans the written
  source from the apply manifest's `changes[].path`, not the manifest JSON.
- **H3 — Plugin integrity** (`plugin_system.py`, `plugin_cmd.py`): `plugin init`
  wrote `plugin.yaml` while every loader reads `plugin.json` (broken round-trip)
  → now writes `plugin.json` with a permissions block; `entry_checksum` is
  stamped on every install (scaffold + download) via `stamp_plugin_integrity`, so
  `load()`'s tamper-check actually verifies. (In-process capability sandboxing of
  executed plugin code remains an absorb-list item — see below.)
- **M2 — Stale call graph** (`harness/runner.py`): post-run reindex used
  `index_file` per file and never finalized cross-file edges; now uses
  `KnowledgeGraph.reindex_files` (re-parse + FTS + cross-file edges).
- **M5 — Markdown memory dedup** (`context_repository.py`): `store()` now skips a
  jaccard near-duplicate (≥0.85, same collection) for auto-stores, so harvest
  summaries that differ only by run id stop accreting.
- **M6 — prefs→yaml bridge** (`menu_cmd.py`, `onboarding/service.py`): the menu
  "Providers & models" action and onboarding now call
  `sync_runtime_prefs_to_yaml`, so chosen provider/model/security reach the
  runtime (it reads them from yaml).
- **M7 — Sampling deadlock** (`mcp_stdio.py`): `_request_sampling` looped on a
  blocking readline with no deadline; now bounded by a select-based timeout
  (falls back to a plain read when stdin has no pollable fd) and treats timeout/
  disconnect/error responses as empty.
- **M8 — No redaction at the MCP boundary** (`mcp_stdio.py`): the tools/call
  envelope and the sampling prompt/system prompt are now run through
  `SecretScanner.redact` before they leave the process.
- **M4 — CLI memory store mismatch** (`main.py`): id-targeted markdown mutations
  (`pin/unpin/expand/promote/demote`) no longer raise a raw `FileNotFoundError`
  on a SQLite id from `memory list` — they report the store mismatch clearly.
- **M9 — Setup entry-point divergence** (`onboarding/service.py`): the managed
  `.gitignore` storage block is now written by the shared `OnboardingService`,
  so a project configured via `opencontext install` no longer commits its local
  binary index.

---

## REMAINING — structural (two-process) work, scoped not faked

### C3 — Host-model sampling: in-process consumer still missing
The transport is now correct and honest: the sampler registers on `initialize`,
the round-trip is timeout-bounded (M7), redacted (M8), and envelope-compliant
(H6). **But the agentic loop still runs in a separate process** (`opencontext
loop`) from the MCP server that holds the live sampler, so `get_host_sampler()`
returns `None` there and generation degrades (now loudly, not silently).
**Remaining fix:** add an in-process `opencontext_run` MCP tool whose handler
builds a `SamplingGateway` from `self._request_sampling` and drives the harness
with it (the runtime, constructed after `initialize`, picks up the registered
sampler — no lazy-gateway change needed). This carries real stdio-reentrancy
design (each phase's sampling call interleaves with the in-flight `tools/call`)
and warrants its own change with a host-simulation test; deliberately not
shipped half-built.

### C4 — Standalone loop apply: codegen executor still missing
ApplyPhase writes only when an executor produced `FileEdit`s; no production entry
point feeds them, so apply runs in `planned` mode and the host agent performs the
edits. This is now **honestly reported** — the loop states whether real source
was written or apply was planned-only (read from the apply manifest) instead of
"Loop complete" reading as "code written". **Remaining fix:** either wire a
codegen executor that turns the gateway's output into `FileEdit`s fed to `run()`,
or keep apply host-agent-driven and finish documenting it as the contract. The
honest reporting is in; the codegen feature is the open decision.

### M1 — Compression rarely fires (deliberately not forced)
`CompressionEngine` runs only on an over-budget required item; typical packs fit,
so it rarely fires. Proactively compressing large items when budget is ample is
**double-edged** (lossy degradation of the flagship pack for no benefit), so it
is intentionally left as-is pending a value-density threshold design rather than
a blanket "compress everything large".

### LOW / dead code (deferred cleanups)
`SDDOrchestrator` (second SDD engine), `EngramMemoryAdapter`/`MemoryDelta`,
`InstallationManager.install` (incl. git-hook), `AgentInstaller.uninstall` stub;
persona↔phase wiring for apply/verify/test; `store_by_topic_key` columns;
`pack .` not auto-indexing; per-phase model routing read nowhere;
`--compress`/`--autonomous`/checkpoints passed but unused; `max_nodes == 20`
treated as default; provider `max_retries`/streaming declared not implemented;
`scope`/`location` cosmetic on `Configurator.configure`.

## Absorb-list (flecos other projects cover)
- **Real local embeddings** — `DeterministicEmbeddingGenerator` is SHA256-seeded
  random vectors; vector search is a semantic no-op even when enabled.
- **Process sandbox for plugins** — `is_allowed`/checksum are declared and now
  stamped/verified at load, but in-process exec gives full privilege; a real
  capability broker / subprocess jail is needed for true enforcement.

---

## Verification
Full suite: **1753 passed, 6 skipped, 0 failed**; ruff clean. Every closed
finding above has a behavioral regression test that fails if the fix is reverted.
Commits are small and single-concern (one finding per commit, tests alongside).
