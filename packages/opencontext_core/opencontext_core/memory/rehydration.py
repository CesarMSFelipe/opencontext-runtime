"""Recursive summarization for memory rehydration.

Recall over-fetches candidate memory, then compresses it down to the prompt
budget so more signal fits the same tokens. The summary is produced by the cheap
``summarize`` role when a model is reachable, and by a deterministic
line-boundary trim otherwise — so rehydration still works (degraded) with no
model bound. Never raises: any model/gateway failure falls back to the trim.
"""

from __future__ import annotations

from typing import Any


def _trim_to_budget(text: str, target_tokens: int) -> str:
    """Trim a markdown block to ``target_tokens``, preserving the most semantically
    important sections FIRST.

    Prior behavior trimmed from the END of the (already best-first) line list,
    which silently removed the spec scenarios and GIVEN/WHEN/THEN sections --
    exactly the parts most useful to the downstream phase (design / tasks).
    This implementation scores every line by importance (headers > RFC-2119
    keywords > GIVEN/WHEN/THEN > spec bullets > prose), keeps the highest-scoring
    lines first, then re-assembles in the ORIGINAL positions so prose still reads
    naturally.

    Importance bands (higher = keep first):
      - '#' / '##' / '###' headers                       : 100
      - '### Requirement:' / '### Scenario:'               : 90
      - MUST / SHALL / SHOULD / MUST NOT                  : 80
      - 'GIVEN ... WHEN ... THEN ...'                       : 70
      - bulleted lines ('- ...')                          : 50
      - prose / other                                     : 10
    """
    from opencontext_core.context.budgeting import estimate_tokens

    if not text:
        return text

    lines = text.split("\n")

    def _importance(line: str) -> int:
        stripped = line.lstrip()
        if stripped.startswith("## ") or stripped.startswith("# "):
            return 100
        if "### Requirement:" in stripped or "### Scenario:" in stripped:
            return 90
        if (
            "MUST" in stripped
            or "SHALL" in stripped
            or "SHOULD" in stripped
            or "MUST NOT" in stripped
        ):
            return 80
        if "GIVEN" in stripped and "WHEN" in stripped and "THEN" in stripped:
            return 70
        if stripped.startswith("- "):
            return 50
        return 10

    # Importance desc, then position asc (keep original ordering within a band).
    ranked = sorted(range(len(lines)), key=lambda i: (-_importance(lines[i]), i))
    chosen: set[int] = set()
    kept: list[str] = []
    for i in ranked:
        line = lines[i]
        if not line.strip():
            # Always keep blank lines so markdown paragraphs stay readable.
            chosen.add(i)
            kept.append(line)
            continue
        candidate_tokens = estimate_tokens("\n".join([*kept, line]))
        if candidate_tokens > target_tokens:
            # Don't break the budget -- but DO ensure the top header is kept.
            if not kept and i == 0:
                chosen.add(i)
                kept.append(line)
            continue
        chosen.add(i)
        kept.append(line)
    # Re-assemble in ORIGINAL order so prose reads naturally after the kept
    # high-importance sections.
    return "\n".join(line for i, line in enumerate(lines) if i in chosen)


def summarize_to_budget(text: str, target_tokens: int, gateway: Any | None = None) -> str:
    """Compress ``text`` to ~``target_tokens``.

    Returns ``text`` unchanged when it already fits. With a gateway, asks the
    cheap ``summarize`` role to condense; falls back to a deterministic
    line-boundary trim when there is no gateway, the model is mock, or it errors.
    """
    from opencontext_core.context.budgeting import estimate_tokens

    if not text.strip() or estimate_tokens(text) <= target_tokens:
        return text

    if gateway is not None:
        try:
            from opencontext_core.models.llm import LLMRequest

            request = LLMRequest(
                prompt=(
                    f"Condense the following project memory to at most {target_tokens} "
                    "tokens. Keep decisions, constraints, and file references; drop "
                    f"repetition and chatter.\n\n{text}"
                ),
                provider="host",
                model="default",
                max_output_tokens=target_tokens,
                context_items=[],
                metadata={"role": "summarize", "task_complexity": "summarize"},
            )
            response = gateway.generate(request)
            out = (getattr(response, "content", "") or "").strip()
            is_real = getattr(response, "provider", "") != "mock" and not out.startswith(
                "Mock response"
            )
            if out and is_real:
                return out
        except Exception:
            pass

    return _trim_to_budget(text, target_tokens)
