"""Token estimation and budget enforcement."""

from __future__ import annotations

from math import ceil

from opencontext_core.config import ContextConfig
from opencontext_core.models.context import ContextItem, TokenBudget


def estimate_tokens(text: str) -> int:
    """Estimate tokens deterministically without provider-specific tokenizers."""

    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, ceil(len(stripped) / 4))


class TokenBudgetManager:
    """Calculates token budgets and selects context without exceeding them."""

    def __init__(self, config: ContextConfig, model: str | None = None) -> None:
        self.config = config
        self.model = model

    def count_tokens(self, text: str) -> int:
        """Count tokens, preferring an accurate tokenizer when available.

        Falls back to the deterministic :func:`estimate_tokens` heuristic when
        no accurate tokenizer (tiktoken) is installed, so behaviour is always
        defined and never depends on an optional dependency being present.
        """

        from opencontext_core.context.tokenization import count_tokens

        return count_tokens(text, model=self.model)

    def calculate(self) -> TokenBudget:
        """Calculate the input-side token budget."""

        available = max(0, self.config.max_input_tokens - self.config.reserve_output_tokens)
        return TokenBudget(
            max_input_tokens=self.config.max_input_tokens,
            reserve_output_tokens=self.config.reserve_output_tokens,
            available_context_tokens=available,
            sections=self.config.sections.as_dict(),
        )

    def budget_for_section(self, section: str) -> int:
        """Return the effective budget for one prompt section."""

        budget = self.calculate()
        section_budget = budget.sections.get(section, 0)
        return min(section_budget, budget.available_context_tokens)

    def select_within_budget(
        self,
        items: list[ContextItem],
        section: str = "retrieved_context",
        *,
        recount: bool = False,
    ) -> tuple[list[ContextItem], list[ContextItem]]:
        """Select items in order until the effective section budget is exhausted.

        When ``recount`` is true, each item's token cost is recomputed from its
        content with the accurate tokenizer (falling back to the heuristic). The
        default keeps the precomputed ``item.tokens`` so existing behaviour and
        estimates are unchanged.
        """

        limit = self.budget_for_section(section)
        selected: list[ContextItem] = []
        discarded: list[ContextItem] = []
        used_tokens = 0
        for item in items:
            item_tokens = self.count_tokens(item.content) if recount else item.tokens
            if used_tokens + item_tokens <= limit:
                selected.append(item)
                used_tokens += item_tokens
            else:
                updated_metadata = dict(item.metadata)
                updated_metadata["discard_reason"] = "token_budget_exceeded"
                discarded.append(item.model_copy(update={"metadata": updated_metadata}))
        return selected, discarded
