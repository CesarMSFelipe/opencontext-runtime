"""Unified Provider Gateway facade (book §25 "Gateway"; PR-012).

Composes, in order, the book pipeline:

    Runtime -> ProviderGateway -> Routing Engine -> Policy Filter
            -> Prompt Builder -> Provider Adapter

on top of the existing substrate (``ModelRoleRouter``,
``ContextFirewall.check_provider_call``, ``CallBudgetManager`` /
``PreLLMQualityGate``, the vendor ``ProviderAdapter`` shim) and adds the book's
gateway contract: capability/strategy routing, bounded fallback/retry on
error/timeout/quota/unsupported-capability, a wired cost ledger, a provider
response cache, structured-output validation, named ``provider.*`` events,
provider receipts, and a ``RuntimeDecision`` recorded per provider choice.

Name-collision note (compat/collisions.py — "ProviderGateway", rule
``namespace``): the legacy ``llm.provider_gateway.ProviderGateway`` adapter shim
is KEPT as-is for the ``runtime.gateway_enabled=False`` path. This class is the
PR-012 unified facade in a DISTINCT package (``providers.gateway``), disambiguated
by package. The facade COMPOSES the shared adapter-build path
(``llm.provider_gateway.build_adapter``) for fallback dispatch — it does not fork
a second adapter table.

Layering (doc 58): this is L7 (Providers, over L3 Policy). The Runtime-Intelligence
feed (L10) is reached only through an injected ``feed`` port, never a direct
import, so the gateway holds no upward dependency.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from time import perf_counter
from typing import Any

from opencontext_core.errors import (
    ProviderError,
    StructuredOutputError,
    WorkflowExecutionError,
)
from opencontext_core.llm.gateway import LLMGateway
from opencontext_core.llm.provider_gateway import build_adapter
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.operating_model.events import ProviderEvent, ProviderEventEmitter
from opencontext_core.operating_model.performance import CostEntry, CostLedger, ModelRoleRouter
from opencontext_core.operating_model.receipts import ProviderReceipt, RunReceiptStore
from opencontext_core.providers.capabilities import ProviderCapability, capabilities_for
from opencontext_core.providers.cost_model import estimate_cost
from opencontext_core.runtime.decision_log import DecisionRecorder
from opencontext_core.runtime.decisions import DecisionKind, RuntimeDecision
from opencontext_core.safety.firewall import ContextFirewall, FirewallBlockedError

# Default fallback order: local-first, terminating in the always-available mock.
_DEFAULT_FALLBACK = ("ollama", "local", "mock")

# Adapter factory signature (provider -> adapter | None). Injectable for tests.
AdapterFactory = Callable[[str], Any]


class ProviderGateway:
    """The one gateway composing routing -> policy -> prompt -> adapter (book §25)."""

    def __init__(
        self,
        base_gateway: LLMGateway,
        *,
        router: ModelRoleRouter | None = None,
        firewall: ContextFirewall | None = None,
        budget_manager: Any = None,
        quality_gate: Any = None,
        ledger: CostLedger | None = None,
        receipts: RunReceiptStore | None = None,
        recorder: DecisionRecorder | None = None,
        emitter: ProviderEventEmitter | None = None,
        cache: Any = None,
        learning: Any = None,
        feed: Callable[..., Any] | None = None,
        retry_limit: int = 2,
        fallback: bool = True,
        fallback_providers: tuple[str, ...] = _DEFAULT_FALLBACK,
        adapter_factory: AdapterFactory = build_adapter,
    ) -> None:
        self._base = base_gateway
        self._router = router
        self._firewall = firewall
        self._budget_manager = budget_manager
        self._quality_gate = quality_gate
        self._ledger = ledger
        self._receipts = receipts
        self._recorder = recorder
        self._emitter = emitter
        self._cache = cache
        self._learning = learning
        self._feed = feed
        self._retry_limit = max(0, retry_limit)
        self._fallback = fallback
        self._fallback_providers = fallback_providers
        self._adapter_factory = adapter_factory

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate(self, request: LLMRequest) -> LLMResponse:
        role = request.metadata.get("role", "generate")
        complexity = request.metadata.get("task_complexity", "standard")
        required = self._required_caps(request)

        # 1. Routing Engine ------------------------------------------------
        route = self._route(role, complexity, request)
        provider, model = route["provider"], route["model"]
        reason = route.get("reason", "routed")
        self._emit(ProviderEvent.SELECTED, provider=provider, model=model, reason=reason)
        self._save_receipt("provider-selection", provider=provider, model=model, reason=reason)
        self._record_decision(
            kind=DecisionKind.provider,
            chosen=f"{provider}/{model}",
            reason=reason,
            request=request,
        )

        # 2. Policy Filter (before ANY dispatch) ---------------------------
        if self._firewall is not None:
            decision = self._firewall.check_provider_call(provider, request.context_items)
            if not decision.allowed:
                self._emit(ProviderEvent.FAILED, provider=provider, error=decision.reason)
                raise FirewallBlockedError(decision.reason, [])

        # 3. Budget gate + consume (parity with BudgetAwareLLMGateway) ------
        self._budget_gate(provider, model, request)

        routed = request.model_copy(update={"provider": provider, "model": model})

        # 4. Provider response cache (book §25) ----------------------------
        cached = self._cache_get(routed)
        if cached is not None:
            self._emit(
                ProviderEvent.COMPLETED, provider=provider, model=model, cache_hit=True
            )
            self._save_receipt(
                "cost", provider=provider, model=model, reason=reason, cache_hit=True
            )
            return cached

        # 5. Fallback / retry loop -----------------------------------------
        tried: set[str] = set()
        retries = 0
        last_error: Exception | None = None
        for attempt in range(self._retry_limit + 1):
            tried.add(routed.provider)
            try:
                # Unsupported capability is a fallback trigger (book §25).
                if required and not (required <= capabilities_for(routed.provider)):
                    raise ProviderError(f"unsupported_capability:{routed.provider}")
                self._emit(ProviderEvent.CALLED, provider=routed.provider, model=routed.model)
                t0 = perf_counter()
                resp = self._dispatch(routed, is_fallback=attempt > 0)
                latency = perf_counter() - t0
                resp = self._validate_structured(resp, request)
                self._record_cost(routed, resp, latency, retries, reason)
                self._emit(
                    ProviderEvent.COMPLETED, provider=routed.provider, model=routed.model
                )
                self._save_receipt(
                    "provider-call",
                    provider=routed.provider,
                    model=routed.model,
                    reason=reason,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    latency_s=latency,
                    retries=retries,
                    estimated_cost=estimate_cost(
                        routed.provider, resp.input_tokens, resp.output_tokens
                    ),
                )
                self._cache_put(routed, resp)
                return resp
            except StructuredOutputError:
                # A contract violation is surfaced, not retried as a transport fault.
                raise
            except (ProviderError, TimeoutError) as exc:
                last_error = exc
                is_timeout = isinstance(exc, TimeoutError)
                self._emit(
                    ProviderEvent.TIMEOUT if is_timeout else ProviderEvent.FAILED,
                    provider=routed.provider,
                    model=routed.model,
                    error=str(exc),
                )
                if not self._fallback or attempt >= self._retry_limit:
                    break
                nxt = self._next_provider(routed, tried, required)
                if nxt is None:
                    break
                retries += 1
                self._emit(
                    ProviderEvent.FALLBACK,
                    provider=nxt["provider"],
                    model=nxt["model"],
                    error=str(exc),
                )
                self._save_receipt(
                    "fallback",
                    provider=nxt["provider"],
                    model=nxt["model"],
                    reason=f"fallback_from:{routed.provider}",
                    retries=retries,
                    error=str(exc),
                )
                self._record_decision(
                    kind=DecisionKind.provider,
                    chosen=f"{nxt['provider']}/{nxt['model']}",
                    reason=f"fallback_from:{routed.provider}:{exc}",
                    request=request,
                )
                routed = routed.model_copy(
                    update={"provider": nxt["provider"], "model": nxt["model"]}
                )
        raise ProviderError(f"provider_fallback_exhausted: {last_error}")

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #

    def _route(self, role: str, complexity: str, request: LLMRequest) -> dict[str, str]:
        if self._router is None:
            return {
                "provider": request.provider,
                "model": request.model,
                "reason": "request_provided",
            }
        route = self._router.route_with_budget(role, complexity)
        route.setdefault("reason", f"strategy:{getattr(self._router, 'strategy', 'balanced')}")
        return route

    def _next_provider(
        self,
        routed: LLMRequest,
        tried: set[str],
        required: frozenset[ProviderCapability],
    ) -> dict[str, str] | None:
        """Pick the next untried fallback provider (local-first, capability-aware)."""

        for candidate in self._fallback_providers:
            if candidate in tried:
                continue
            if required and not (required <= capabilities_for(candidate)):
                continue
            return {"provider": candidate, "model": routed.model}
        return None

    @staticmethod
    def _required_caps(request: LLMRequest) -> frozenset[ProviderCapability]:
        raw = request.metadata.get("required_capabilities")
        if not raw:
            return frozenset()
        caps: set[ProviderCapability] = set()
        for value in raw:
            try:
                caps.add(ProviderCapability(value))
            except ValueError:
                continue
        return frozenset(caps)

    # ------------------------------------------------------------------ #
    # Budget gate (parity with runtime.BudgetAwareLLMGateway)
    # ------------------------------------------------------------------ #

    def _budget_gate(self, provider: str, model: str, request: LLMRequest) -> None:
        if self._quality_gate is None or self._budget_manager is None:
            return
        report = self._quality_gate.evaluate(
            context_tokens=0,
            max_tokens=1_000_000,
            provider_allowed=True,
            source_count=len(request.context_items),
            budget_manager=self._budget_manager,
            provider=provider,
            model=model,
        )
        budget_risks = [r for r in report.risks if r.startswith("call_budget")]
        if budget_risks:
            raise WorkflowExecutionError(
                f"Call blocked by budget quality gate: {report.reason} - {budget_risks}"
            )
        self._budget_manager.consume(provider, model)

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    def _dispatch(self, request: LLMRequest, *, is_fallback: bool) -> LLMResponse:
        # Primary attempt drives the configured base gateway (preserves host MCP
        # sampling / mock). A fallback dispatches directly to the routed
        # provider's adapter via the shared build path.
        if not is_fallback:
            return self._base.generate(request)
        adapter = self._adapter_factory(request.provider)
        if adapter is None:
            raise ProviderError(f"no_adapter_for_provider:{request.provider}")
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        resp = adapter.chat_with_retries(
            messages, model=request.model, max_tokens=request.max_output_tokens
        )
        return LLMResponse(
            content=resp.content,
            provider=resp.provider or request.provider,
            model=resp.model or request.model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            metadata=resp.metadata or {},
        )

    # ------------------------------------------------------------------ #
    # Structured-output validation (PG-CONV)
    # ------------------------------------------------------------------ #

    def _validate_structured(self, resp: LLMResponse, request: LLMRequest) -> LLMResponse:
        schema = request.metadata.get("response_schema")
        if not schema:
            return resp
        try:
            payload = json.loads(resp.content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise StructuredOutputError(f"response_not_json: {exc}") from exc
        expected_type = schema.get("type")
        if expected_type == "object" and not isinstance(payload, dict):
            raise StructuredOutputError("response_not_object")
        if expected_type == "array" and not isinstance(payload, list):
            raise StructuredOutputError("response_not_array")
        for field in schema.get("required", []):
            if not isinstance(payload, dict) or field not in payload:
                raise StructuredOutputError(f"missing_required_field:{field}")
        return resp

    # ------------------------------------------------------------------ #
    # Cost ledger + Runtime-Intelligence feed (best-effort, non-blocking)
    # ------------------------------------------------------------------ #

    def _record_cost(
        self,
        routed: LLMRequest,
        resp: LLMResponse,
        latency: float,
        retries: int,
        reason: str,
    ) -> None:
        try:
            if self._ledger is not None:
                self._ledger.record(
                    CostEntry(
                        workflow=routed.metadata.get("workflow", "provider_call"),
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                        estimated_cost=estimate_cost(
                            routed.provider, resp.input_tokens, resp.output_tokens
                        ),
                        actual_latency=latency,
                        provider=routed.provider,
                        model=routed.model,
                        routing_reason=reason,
                        retries=retries,
                    )
                )
            if self._feed is not None:
                self._feed(
                    self._learning,
                    operation_type="provider_call",
                    query=str(routed.metadata.get("query", ""))[:200],
                    tokens_used=resp.input_tokens + resp.output_tokens,
                    success=True,
                    outcome=None,
                )
        except Exception:
            # Metrics are best-effort (design DEC-7): never change the call outcome.
            return

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #

    def _cache_context(self, routed: LLMRequest) -> str:
        return "\n".join(item.content for item in routed.context_items)

    def _cache_get(self, routed: LLMRequest) -> LLMResponse | None:
        if self._cache is None or not getattr(self._cache, "enabled", False):
            return None
        try:
            hit = self._cache.get(
                provider=routed.provider,
                model=routed.model,
                prompt_version=str(routed.metadata.get("prompt_version", "v1")),
                user_input=routed.prompt,
                context=self._cache_context(routed),
            )
        except Exception:
            return None
        if hit is None:
            return None
        return LLMResponse(
            content=hit,
            provider=routed.provider,
            model=routed.model,
            input_tokens=0,
            output_tokens=0,
            metadata={"cache_hit": True},
        )

    def _cache_put(self, routed: LLMRequest, resp: LLMResponse) -> None:
        if self._cache is None or not getattr(self._cache, "enabled", False):
            return
        try:
            self._cache.put(
                provider=routed.provider,
                model=routed.model,
                prompt_version=str(routed.metadata.get("prompt_version", "v1")),
                user_input=routed.prompt,
                context=self._cache_context(routed),
                response=resp.content,
                system_prompt=routed.system_prompt or None,
            )
        except Exception:
            return

    # ------------------------------------------------------------------ #
    # Events / receipts / decisions
    # ------------------------------------------------------------------ #

    def _emit(self, event: ProviderEvent, **payload: object) -> None:
        if self._emitter is not None:
            self._emitter.emit(event, **payload)

    def _save_receipt(
        self,
        kind: str,
        *,
        provider: str,
        model: str = "",
        reason: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_s: float = 0.0,
        retries: int = 0,
        estimated_cost: float = 0.0,
        cache_hit: bool = False,
        error: str | None = None,
    ) -> None:
        if self._receipts is None:
            return
        try:
            self._receipts.save_provider_receipt(
                ProviderReceipt(
                    kind=kind,  # type: ignore[arg-type]
                    provider=provider,
                    model=model,
                    routing_reason=reason,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_s=latency_s,
                    retries=retries,
                    estimated_cost=estimated_cost,
                    cache_hit=cache_hit,
                    error=error,
                )
            )
        except Exception:
            return

    def _record_decision(
        self,
        *,
        kind: DecisionKind,
        chosen: str,
        reason: str,
        request: LLMRequest,
    ) -> None:
        if self._recorder is None:
            return
        try:
            self._recorder.record(
                RuntimeDecision(
                    kind=kind,
                    chosen=chosen,
                    reason=reason,
                    run_id=request.metadata.get("run_id"),
                )
            )
        except Exception:
            return
