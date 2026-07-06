# MEMORY_CONTRACT

Agentic memory must improve later runs and save tokens — reusable, auditable, and purgable.
A memory that cannot be explained, approved, or deleted does not belong in the store.

Verified by: AC-017, AC-018, AC-019, AC-028, MEM-001..MEM-009.

## Types

`fact`, `decision`, `preference`, `constraint`, `pattern`, `failure`, `solution`,
`project_context`.

## States

| State | Meaning | Current mapping |
|---|---|---|
| `proposed` | Harvested candidate, not yet trusted | `collect`/`harvest` output; review queue |
| `approved` | Usable in context packs and runs | active memory (post `promote`/review confirm) |
| `rejected` | Explicitly discarded; never retrieved | deleted/`demote`d out |
| `expired` | Aged out by retention policy | stale / `needs_review` (via `review`, decay in `maintain`) |
| `compacted` | Summarized into a smaller record | consolidation in `maintain`; superseded records point to the summary |
| `purged` | Physically removed | `prune` / `gc` / uninstall purge |

> Current → Target: the current lifecycle vocabulary is active / stale (`needs_review`) /
> superseded plus tiers (`promote`/`demote`) and pins. The six canonical states above are the
> freeze target; the mapping column is the migration guide.

## Lifecycle flow

```
harvest after run → propose memory delta → classify → deduplicate
→ require approval when configured → save → retrieve in future pack
→ report usage → compact/expire → purge on uninstall
```

## Rules

1. No secrets are ever stored; redaction runs before save (AC-028).
2. `store_raw: false` is honored — no raw prompts persisted.
3. Unapproved (`proposed`) memory is not used in packs/runs unless configuration explicitly
   allows it (`memory.approval_required: false`).
4. Every memory hit used by a run is recorded in `run.json`:

```json
{
  "memory": {
    "used": true,
    "hits": [
      {"id": "mem_123", "type": "project_context", "score": 0.91, "used_for": "test command selection"}
    ],
    "new_candidates": 2,
    "requires_approval": true
  }
}
```

5. Explainability: when memory influences a decision, the pack/report must be able to say
   which memory and why (`used_for`).
6. Deduplication by content hash/semantic similarity; compaction preserves pinned and
   decision-type records (MEM-005, MEM-006).
7. Uninstall with `--purge` removes managed memory stores (MEM-008).

## Command surface

Real (stable candidates):

```
opencontext memory save* | search | expand | show | pin | unpin
                  | collect | harvest | promote | demote
                  | prune | gc | maintain | review | doctor
                  | export | import | audit
```

\* `save` (plus `search/context/get/update/...`) currently lives under the `memory v2`
namespace: `opencontext memory v2 save|search|context|get|...`.

Planned additions (target, not yet implemented):

```
opencontext memory approve <id>   # proposed → approved
opencontext memory reject <id>    # proposed → rejected
opencontext memory compact        # summarize old entries, keep protected ones
opencontext memory purge          # remove everything managed (explicit confirm)
```

> Current → Target: `approve`/`reject` map today onto `review` (confirm/correct) and
> `promote`/`demote`; `compact` maps onto `maintain` consolidation; `purge` maps onto
> `prune`+`gc`+uninstall purge. The dedicated verbs above become thin, stable aliases so the
> approval lifecycle is a first-class CLI contract (AC-018, AC-019).
