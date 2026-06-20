from __future__ import annotations

from opencontext_core.operating_model import CallBudgetConfig, CallBudgetManager, ModelRoleRouter


def test_model_role_router_defaults_to_mock() -> None:
    assert ModelRoleRouter().route("critic") == {"provider": "mock", "model": "mock-llm"}


def test_model_role_router_with_budget_delegates_simple_tasks_to_local() -> None:
    config = CallBudgetConfig(local_preference_threshold=5)
    manager = CallBudgetManager(config=config)
    router = ModelRoleRouter(budget_manager=manager)

    result = router.route_with_budget("generate", task_complexity="summarize")
    assert result["provider"] in ["ollama", "lmstudio", "localai", "mock"]


def test_model_role_router_with_budget_uses_paid_for_complex() -> None:
    config = CallBudgetConfig(local_preference_threshold=5)
    manager = CallBudgetManager(config=config)
    router = ModelRoleRouter(
        roles={"generate": {"provider": "openai", "model": "gpt-4"}},
        budget_manager=manager,
    )

    result = router.route_with_budget("generate", task_complexity="complex_reasoning")
    assert result["provider"] == "openai"


def test_model_role_router_substitutes_local_model_on_delegate() -> None:
    # A simple-task delegate to a local provider must not carry the paid model name
    # (gpt-4o), which would 404 against a local backend like ollama.
    router = ModelRoleRouter(
        roles={"generate": {"provider": "openai", "model": "gpt-4o"}},
        budget_manager=CallBudgetManager(),
    )
    result = router.route_with_budget("generate", task_complexity="summarize")
    assert result["provider"] in ("ollama", "lmstudio", "localai")
    assert result["model"] != "gpt-4o"


def test_model_role_router_delegates_when_budget_low() -> None:
    config = CallBudgetConfig(local_preference_threshold=5)
    manager = CallBudgetManager(config=config)

    for _ in range(200):
        manager.consume("openai", "gpt-4")

    router = ModelRoleRouter(
        roles={"generate": {"provider": "openai", "model": "gpt-4"}},
        budget_manager=manager,
    )

    result = router.route_with_budget("generate", task_complexity="standard")
    assert result["provider"] in ["ollama", "lmstudio", "localai", "mock"]
