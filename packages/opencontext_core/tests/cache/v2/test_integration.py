"""Integration test: all PR-008..017 modules fully functional."""

from __future__ import annotations


class TestAllModules:
    def test_cache_leaf_all_strategies(self) -> None:
        from opencontext_core.cache.v2 import CacheStrategy, SemanticCache
        for s in CacheStrategy:
            c = SemanticCache(s, max_entries=3)
            c.set("k", 42)
            assert c.get("k") == 42

    def test_memory_harness_pipeline(self) -> None:
        from opencontext_core.memory.v2.harness import MemoryHarnessV2
        mh = MemoryHarnessV2(quality_threshold=0.0)
        result = mh.ingest([
            {"id": 1, "topic_key": "a", "type": "x", "content": "hello world " * 20},
            {"id": 2, "topic_key": "a", "type": "x", "content": "different"},
        ])
        assert len(result.conflicts) == 1
        assert result.ingested == 2

    def test_decision_log_full(self) -> None:
        from opencontext_core.decision_log.recorder import (
            DecisionLogEntry,
            DecisionRecorder,
            NoCoTExtractor,
            brain_no_write_port_guard,
        )
        assert brain_no_write_port_guard() is True
        ext = NoCoTExtractor()
        entries = ext.extract("We decided to use hexagonal architecture for the API layer")
        assert len(entries) >= 1
        d = DecisionRecorder(confidence_threshold=0.5)
        d.record(DecisionLogEntry(id="d1", kind="architecture", decision="hexagonal", confidence=0.8))
        assert d.promote("d1")

    def test_context_v2_full(self) -> None:
        from opencontext_core.context.v2.envelope import (
            ContextCompressor,
            ContextEnvelope,
            ContextRanker,
            usefulness_score,
        )
        e = ContextEnvelope(task="auth bug", items=[
            {"content": "login returns 500", "id": "i1"},
            {"content": "unrelated docs", "id": "i2"},
        ], budget=100)
        r = ContextRanker()
        ranked = r.rank(e.items, "auth")
        assert len(ranked) == 2
        score = usefulness_score({"content": "login bug fix"}, "login bug")
        assert score > 0.0
        comp = ContextCompressor()
        e2 = comp.compress(e, target_tokens=5)
        assert e2.compressed

    def test_runtime_intel_full(self) -> None:
        from opencontext_core.runtime.intel.calibration import (
            CalibrationEntry,
            ConfidenceCalibrator,
        )
        from opencontext_core.runtime.intel.simulator import (
            CostEstimator,
            HealthChecker,
            RuntimeProfiler,
            WorkflowSimulator,
        )
        ws = WorkflowSimulator()
        r = ws.simulate("sdd", "add auth")
        assert r.token_estimate > 0
        ce = CostEstimator()
        assert ce.estimate(1000) == 2.0
        cc = ConfidenceCalibrator()
        # new API: Brier-style score from a (confidence, outcome) history
        history = [CalibrationEntry(confidence=0.8, outcome=0.8) for _ in range(20)]
        score = cc.calibrate(history)
        assert score == 0.0
        rp = RuntimeProfiler()
        rp.record(r)
        assert rp.avg_cost > 0
        hc = HealthChecker()
        assert hc.check()["kg_v2"] == "ok"

    def test_provider_gateway_full(self) -> None:
        from opencontext_core.providers.v2.gateway import (
            FallbackRouter,
            ProviderCapability,
            ProviderGateway,
            StructuredOutputAdapter,
        )
        gw = ProviderGateway()
        gw.register("mock", ProviderCapability(name="mock", models=["mock-llm"]))
        assert gw.best_for(min_tokens=1000) is not None
        fr = FallbackRouter(gw)
        assert fr.route("nonexistent", ["mock"]) == "mock"
        adapt = StructuredOutputAdapter()
        assert adapt.adapt({"a": 1, "b": 2}, {"a": None}) == {"a": 1}

    def test_studio_full(self) -> None:
        from opencontext_core.studio.server import StudioServer
        s = StudioServer()
        assert len(s.list_timelines()) == 11
        assert len(s.list_views()) == 6

    def test_plugins_full(self) -> None:
        from opencontext_core.plugins.sdk import (
            PluginConformance,
            PluginError,
            PluginManifest,
            PluginRegistry,
            PluginState,
        )
        pr = PluginRegistry()
        m = PluginManifest(name="test", version="1.0", endpoints=1, permissions=["read"])
        pr.register(m)
        pr.transition("test", PluginState.LOADED)
        pr.transition("test", PluginState.RUNNING)
        try:
            pr.transition("test", PluginState.REGISTERED)
        except PluginError:
            pass
        conf = PluginConformance()
        assert not conf.check(m)

    def test_marketplace_full(self) -> None:
        from opencontext_core.marketplace.registry import (
            OFFICIAL_PACKS,
            MarketPackage,
            MarketRegistry,
        )
        mr = MarketRegistry()
        mr.register(MarketPackage(name="bench-tool", version="1.0"))
        mr.benchmark_on_install("bench-tool", 0.95)
        results = mr.search("bench")
        assert len(results) == 1
        assert "bench-tool" in OFFICIAL_PACKS

    def test_benchmarks_full(self) -> None:
        from opencontext_core.benchmarks.runner import BenchRunner
        br = BenchRunner()
        results = br.run_all_suites(runs=10)
        assert len(results) == 7
        v = br.verdict()
        assert v["total"] == 7
        assert v["passed"] == 7
        issues = br.release_lint()
        assert not issues
