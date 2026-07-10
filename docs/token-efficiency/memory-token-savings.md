# Memory: Progressive, Ranked Recall

## Purpose
Progressive memory injects pinned and relevant compact memory only, while omitted and expandable items remain available by id.

## Current Status
Implemented through progressive disclosure memory selection. Pinned and relevant compact memories
are injected first; omitted memories remain available by id for explicit expansion. Search is
multi-signal and traceable, and memory content is redacted before storage.

## Recursive summarization at rehydration
Memory recall over-fetches candidate items (3x the prompt budget) and then compresses them back to
the budget. Because items are ranked before compression, the highest-signal memories survive within
the same rehydration budget — the mechanism is better ranked recall, not a net token cut.
Compression uses the cheap `summarize`
role when a model is bound, and a deterministic line-boundary trim otherwise (items are ranked, so
the trim keeps the top ones). It is a no-op when recall already fits, and never raises. Implemented
in `memory/rehydration.py`, wired into `OpenContextRuntime._recall_memory_for_prompt`.

## Adaptive retrieval budget (ACON-lite)
The token optimizer widens the retrieval budget for an operation type when its history shows
failures that coincided with omitted context — evidence the pack was over-compressed — instead of
only shrinking toward average usage. The boost is bounded (+50%) and a clean history leaves the
budget unchanged. The harness records each run's outcome alongside its omission count so the signal
is available; budgets are recomputed by `optimize_budgets()`. Implemented in
`learning/token_optimizer.py`.

## Related Commands
```bash
opencontext tokens report .
opencontext inspect repomap --format toon
opencontext pack . --query "review auth" --format compact_table
opencontext cache plan --query "review auth"
opencontext ask "Summarize project" --output-mode technical_terse
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/context/`
- `packages/opencontext_core/opencontext_core/memory_usability/`
- `packages/opencontext_core/opencontext_core/operating_model/performance.py`
