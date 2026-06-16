# Ai Team Operating Model

## Purpose
A team-grade AI operating layer compiles context, policy, tools, memory, approvals, cache, and evaluation into repeatable workflows.

## Current Status
Local scaffolds are implemented for command registry, hook registry, approvals, playbooks, baselines, run receipts, and reports. They do not execute external actions by default.

## Call Budget Management
The system tracks and limits API calls to prevent quota exhaustion:

- **CallBudgetManager**: Tracks calls per provider/model with configurable limits (default 200 per 24h window)
- **ProviderType**: Categorizes providers (LOCAL, FREE, PAID, FREE_TIER)
- **Local Fallback**: Automatically switches to local providers (Ollama, LMStudio, LocalAI) when paid quotas drop below threshold
- **Task Complexity Routing**: Simple tasks (summarize, format, classify, extract, translate) are delegated to local models
- **Free Provider Registry**: Lists available free/opensource providers from [free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources)

### Usage Example
```python
from opencontext_core.operating_model import CallBudgetManager, CallBudgetConfig, ModelRoleRouter

# Configure with 200-call limit per provider
config = CallBudgetConfig(
    default_limit=200,
    local_preference_threshold=50,  # Switch to local when <50 calls remain
    strict_mode=True
)
budget = CallBudgetManager(config)
router = ModelRoleRouter(roles={"generate": {"provider": "openai", "model": "gpt-4"}}, budget_manager=budget)

# Route will prefer local for simple tasks
result = router.route_with_budget("generate", task_complexity="summarize")
# Returns {"provider": "ollama", "model": "gpt-4"} to save quota
```

## Related Commands
```bash
opencontext playbooks list
opencontext command run review-pr
opencontext approvals list
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/operating_model/team.py`
- `packages/opencontext_core/opencontext_core/operating_model/call_budget.py`
- `packages/opencontext_core/opencontext_core/operating_model/performance.py`
