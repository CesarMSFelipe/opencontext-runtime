"""v2 benchmark extension tests."""


def test_v2_quality_metric_keys_exist():
    """New quality metric keys exist in benchmark output schema."""
    from opencontext_core.evaluation.benchmark_suite import V2_QUALITY_METRICS

    required_keys = {
        "context_contract_completeness",
        "validation_gate_pass_rate",
        "memory_hit_rate",
        "tier_distribution",
    }
    assert required_keys.issubset(set(V2_QUALITY_METRICS.keys()))


def test_tier_distribution_has_required_tiers():
    """tier_distribution contains cheap, precise, and critical."""
    from opencontext_core.evaluation.benchmark_suite import V2_QUALITY_METRICS

    tier_dist = V2_QUALITY_METRICS["tier_distribution"]
    assert isinstance(tier_dist, dict)
    for tier in ("cheap", "precise", "critical"):
        assert tier in tier_dist


def test_contract_build_latency_completes_without_crash():
    """contract_build_latency scenario completes without crash."""
    from opencontext_core.evaluation.benchmark_suite import contract_build_latency_benchmark

    result = contract_build_latency_benchmark()
    assert isinstance(result, dict)
    assert result["scenario"] == "contract_build_latency"
    # Status is ok or error — either way no exception raised
    assert result["status"] in ("ok", "error")


def test_contract_build_latency_returns_timing():
    """contract_build_latency returns a duration_ms value."""
    from opencontext_core.evaluation.benchmark_suite import contract_build_latency_benchmark

    result = contract_build_latency_benchmark()
    assert "duration_ms" in result
    # If successful, duration must be non-negative
    if result["status"] == "ok":
        assert result["duration_ms"] >= 0
