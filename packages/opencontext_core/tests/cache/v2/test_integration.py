"""Integration test: all PR-008..017 modules importable and functional."""

from __future__ import annotations


def test_cache_leaf_isolated() -> None:
    from opencontext_core.cache.v2 import SemanticCache
    c = SemanticCache()
    c.set("x", 1)
    assert c.apply_delta({"x"}) == 1

def test_memory_harness_v2() -> None:
    from opencontext_core.memory.v2.harness import MemoryHarnessV2
    mh = MemoryHarnessV2()
    conflicts = mh.detect_conflicts([
        {"id": 1, "topic_key": "a", "type": "x", "content": "hello"},
        {"id": 2, "topic_key": "a", "type": "x", "content": "world"},
    ])
    assert len(conflicts) == 1

def test_decision_log() -> None:
    from opencontext_core.decision_log.recorder import DecisionRecorder, DecisionLogEntry
    d = DecisionRecorder(confidence_threshold=0.0)
    d.record(DecisionLogEntry(id="d1", kind="architecture", decision="test", confidence=0.8))
    assert d.promote("d1")

def test_context_v2() -> None:
    from opencontext_core.context.v2.envelope import ContextEnvelope, ContextRanker, ContextRouter
    e = ContextEnvelope(task="test")
    r = ContextRanker()
    assert r.rank([], "q") == []

def test_runtime_intel() -> None:
    from opencontext_core.runtime.intel.simulator import WorkflowSimulator, CostEstimator
    ws = WorkflowSimulator()
    r = ws.simulate("sdd", "add auth")
    assert r.token_estimate > 0

def test_provider_gateway() -> None:
    from opencontext_core.providers.v2.gateway import ProviderGateway, ProviderCapability, FallbackRouter
    gw = ProviderGateway()
    gw.register("mock", ProviderCapability(name="mock", models=["mock-llm"]))
    router = FallbackRouter(gw)
    assert router.route("mock") == "mock"

def test_studio() -> None:
    from opencontext_core.studio.server import StudioServer
    s = StudioServer()
    assert s.status()["studio"] == "running"

def test_plugins() -> None:
    from opencontext_core.plugins.sdk import PluginRegistry, PluginManifest
    pr = PluginRegistry()
    pr.register(PluginManifest(name="test", version="1.0"))
    assert len(pr.list()) == 1

def test_marketplace() -> None:
    from opencontext_core.marketplace.registry import MarketRegistry, MarketPackage
    mr = MarketRegistry()
    mr.register(MarketPackage(name="bench-tool", version="1.0"))
    assert len(mr.search("bench")) == 1

def test_benchmarks() -> None:
    from opencontext_core.benchmarks.runner import BenchRunner
    br = BenchRunner()
    br.run("A1-baseline", runs=10)
    v = br.verdict()
    assert v["passed"] == 1
