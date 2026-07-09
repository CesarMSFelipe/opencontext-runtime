# Context-packing size benchmarks

Real, reproducible measurements of context-packing size: OpenContext's one-call
pack vs. reading the relevant files whole. Every number here comes from running
OpenContext against public repositories at pinned commits — nothing is
hand-authored. This is a packing-size comparison, **not** an end-to-end token,
latency, or task-success claim; on a small surgical task a targeted read of one
file can cost fewer tokens than a full pack. Raw data:
[`results.json`](results.json).

## Results

Measured 2026-06-30. Budget: 16,000 tokens (the `precise` risk tier). Tokenizer:
`opencontext_core.context.tokenization.count_tokens` (the same counter for both
sides of every comparison).

| Repository | Python files | Task | OpenContext pack | Read relevant files whole | Fewer tokens |
|---|--:|---|--:|--:|--:|
| [psf/requests](https://github.com/psf/requests) `@23953c0` | 37 | fix retry logic when the connection drops | 15,691 | 44,494 | **65%** |
| [psf/requests](https://github.com/psf/requests) `@23953c0` | 37 | verify SSL certificate validation | 12,499 | 40,834 | **69%** |
| [tiangolo/fastapi](https://github.com/tiangolo/fastapi) `@702fea8` | 1,129 | add OAuth2 bearer token authentication | 12,932 | 22,477 | **42%** |
| [django/django](https://github.com/django/django) `@7b09ce8` | 2,924 | how the ORM compiles a QuerySet into SQL | 14,728 | 117,057 | **87%** |

Range across these tasks: the pack is **42–87% smaller** than reading those files
whole. The reduction grows with repo
and file size — a small library (requests) and a focused feature (fastapi OAuth2,
where the relevant files are already small) gain less; a large codebase with big
modules (django's ORM: `query.py`, `sql/compiler.py`, `sql/query.py` are
~25–31k tokens each) gains the most.

## What is measured

- **OpenContext pack** — `opencontext pack --query "<task>" --max-tokens 16000`.
  The symbol-level, call-graph-ranked context OpenContext returns in one call.
  `pack_tokens` is the pack's reported `used_tokens`.
- **Read relevant files whole** — the baseline. For the source (`.py`) files the
  pack drew from, the cost of reading each one in full (same token counter),
  summed. This is the honest "you'd have to open these files" comparison.
- **Fewer tokens** — `(baseline − pack) / baseline`.

This isolates one thing: tokens to put the relevant code in front of a model,
symbol-level vs whole-file. It is **not** a model-quality, latency, or
end-task-success claim, and it does not model multi-round grep+read agent loops
(which would only widen the gap).

## Reproduce

```bash
git clone https://github.com/psf/requests && cd requests
git checkout 23953c0
opencontext index .
opencontext pack --query "fix retry logic when the connection drops" \
  --max-tokens 16000 --format json . | python -c "import json,sys;print(json.load(sys.stdin)['used_tokens'])"
```

Then compare against the whole-file token totals of the files the pack lists
under `included`. Full per-file numbers for every case are in
[`results.json`](results.json) (`baseline_file_tokens`).
