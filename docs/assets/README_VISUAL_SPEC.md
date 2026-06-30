# README visual spec (1.5.0 landing)

Turn the README into a GitHub-native product landing page: SVG-first, honest by
default, one message — **OpenContext builds verified, deterministic code context
before your AI coding agent acts.** Long reference material lives in `docs/`.

Delivered in two layers. The **blocker layer** (truthfulness, scripts, install,
claims) gates the release. The **polish layer** (new art, animation, demo GIFs,
benchmark-from-data) is incremental and may land after.

## Visual system

Widths: main `720`; tall showcase `720×360`; strips `720×48|72`; cards `720×180`;
terminal captures `720×300`.

Palette: bg `#0B0F14` · card `#111821` · border `#21262D` · text `#E6EDF3` ·
muted `#9DA6B0` · teal `#2DC4A4` · blue `#35ADE5` · amber `#D4A840` · purple
`#8A6BBF` · red only for blocked / fail-closed states.

Rules:
- Every meaningful SVG has `role="img"` + an accurate `aria-label`. Decorative
  assets (`logo.svg`) use empty `alt=""` in the README instead.
- Every visual claim is mirrored in nearby text. No claim lives only in an image.
- Static SVG for diagrams; GIF/WebM only for real CLI/process demos.
- Keep assets < ~150 KB; the rendered README must stay < 500 KiB (GitHub truncates).
- Reference `docs/assets/...`; do not inline large SVGs.

## README scene order

1. Hero · 2. Install (30s) · 3. Live demo · 4. The OpenContext difference ·
5. Offline vs model · 6. Runtime pipeline · 7. ContextContract + AICX ·
8. Local code graph · 9. Agent interface · 10. SDD/TDD harness ·
11. Proof, not promises · 12. Security defaults · 13. Memory · 14. Core commands ·
15. Maturity, limitations & tested claims · 16. Docs / License / Contributing.

## Asset manifest

| Asset | Status | Notes |
|-------|--------|-------|
| `logo.svg`, `runtime-strip.svg` | exists | strip alt corrected to "claims tested" |
| `pipeline.svg` | exists | base for an optional `pipeline-animated.svg` (decorative motion only) |
| `local-code-graph.svg`, `mcp-tools.svg`, `sdd-phases.svg`, `tdd-phases.svg`, `benchmark-numbers.svg`, `security-defaults.svg`, `difference-card.svg` | exists | keep |
| `hero-runtime.svg` | created | agent → runtime → verified pack, four lanes (graph/budget/gates/pack); wired into the hero |
| `install-path.svg` | skipped | duplicates existing `quickstart-flow.svg` (install → demo → editor → ready) |
| `offline-model-matrix.svg` | created | visualizes the offline-vs-model table (4 cards); wired below that table |
| `mcp-interface-map.svg` | skipped | duplicates existing `mcp-tools.svg` (the 19-tool group map) |
| `release-trust.svg` | created | stable / opt-in / host-dependent / scaffolded-fail-closed + `pytest tests/smoke/test_readme_claims.py`; wired into Maturity |
| `demo-*.gif` / `*.webm` | to record | install, explain, kept-out, mcp-run, benchmark — **requires screen recording (manual/CI), not generatable from code** |
| benchmark card SVGs | regenerate | must be generated from saved `opencontext benchmark run --format markdown/json` output, not hand-edited; store raw results under `docs/benchmarks/results/` |

## Status

**Blocker layer — DONE (this change):**
- `install.sh` / `install.ps1` version 1.2.0 → 1.5.0.
- Offline-vs-model table split: MCP read/quality/memory tools are offline; only
  `opencontext_run` uses the host model via sampling.
- Agentic Harness "Requires an LLM provider" → host-model / provider / honest
  planned-only wording.
- `runtime-strip` alt "2300+ tests" → "claims tested".
- Install simplified to pipx-first; the full method matrix moved to
  `docs/getting-started/installation.md`.
- Hygiene: README < 500 KiB, all asset links resolve, meaningful SVGs carry
  `role`/`aria-label`.

**Polish layer — DONE (this change):**
- Authored 3 of the 5 candidate SVGs on the palette/canvas system and wired them
  into the README: `hero-runtime.svg` (hero), `offline-model-matrix.svg` (offline
  section), `release-trust.svg` (Maturity). The other two (`install-path`,
  `mcp-interface-map`) were dropped — they duplicate `quickstart-flow.svg` and
  `mcp-tools.svg`; adding them would be redundant art, not new signal.
- `runtime-strip.svg` rendered text corrected "2300+ tests" → "claims tested"
  (the README alt was already corrected in the blocker layer).
- All meaningful SVGs carry `role`/`aria-label`; README is 31 KiB (< 500 KiB);
  every asset link resolves; all SVGs parse as well-formed XML.

**Polish layer — STILL PENDING (needs tools not available here):**
- Record the demo GIFs (manual — needs a terminal recorder; cannot be produced
  from source).
- Generate benchmark card SVGs from reproducible `opencontext benchmark run`
  output committed under `docs/benchmarks/results/`.
- Optional animated `pipeline-animated.svg` (decorative only; the static state
  must still explain the full process).
- Full scene reorder of the README body to the 16-section order above.
