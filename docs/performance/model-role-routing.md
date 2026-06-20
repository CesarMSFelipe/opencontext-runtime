# Model Role Routing

## Choosing models (recommended: per persona)
OpenContext runs on top of your agent CLI, which fixes the **provider**. You
choose which **model** each part of the SDD flow uses; it is sent to the agent as
an MCP sampling hint. The recommended axis is **per persona** — each persona owns
its SDD phase(s), so it reads naturally:

```bash
opencontext models set-persona architect opus     # design phase
opencontext models set-persona explorer  haiku    # explore phase
opencontext models set-default sonnet              # everything else
opencontext models show                            # persona -> phase -> model
```

`default` means **your client's selected model** — the out-of-the-box behavior,
with no model picked for you. At install you pick a preset
(`default` / `cheap` / `hybrid` / `premium`); `default` keeps the client's model
for every phase.

There are two independent axes (both fall back to `default` = the client's model):

- **Per persona** (`set-persona`) routes the **SDD phases** of the dev loop
  (explore/design/apply/…). Resolution: SDD profile → persona override →
  explicit `models.phases` override.
- **Per role** (`set-role`) routes **functional operations** outside the phase
  loop (classify, retrieve, rerank, compress, generate, validate, …), e.g. in
  `ask`/retrieval. This is a separate axis, not a fallback of per-persona.

## Purpose
ModelRoleRouter maps classifier, retriever, compressor, generator, critic, and verifier roles to provider/model aliases.

## Current Status
Implemented as local deterministic scaffolds; provider-specific cache and cost integrations are future adapters outside core.

## Related Commands
```bash
opencontext cache plan --query "review auth"
opencontext cache warm --workflow code-review
opencontext report cost
opencontext harness run --workflow explore-only --task "security audit"
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/operating_model/performance.py`
