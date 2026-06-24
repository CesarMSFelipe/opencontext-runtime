from __future__ import annotations

from opencontext_core.operating_model import RunReceiptGenerator


def test_run_receipt_generator_hashes_artifacts() -> None:
    receipt = RunReceiptGenerator().generate(
        workflow_id="review",
        policy="policy",
        context_pack="context",
        prompt="prompt",
        provider="mock",
        model="mock-llm",
        trace_id="trace",
        input_tokens=1,
        output_tokens=2,
    )

    assert receipt.policy_hash != "policy"
    assert receipt.prompt_hash != "prompt"


def test_run_receipt_generator_default_quality_status_none() -> None:
    receipt = RunReceiptGenerator().generate(
        workflow_id="review",
        policy="p",
        context_pack="c",
        prompt="x",
        provider="mock",
        model="mock-llm",
        trace_id="t",
        input_tokens=1,
        output_tokens=2,
    )
    assert receipt.quality_status is None


def test_run_receipt_generator_records_quality_status() -> None:
    receipt = RunReceiptGenerator().generate(
        workflow_id="review",
        policy="p",
        context_pack="c",
        prompt="x",
        provider="mock",
        model="mock-llm",
        trace_id="t",
        input_tokens=1,
        output_tokens=2,
        quality_status="passed",
    )
    assert receipt.quality_status == "passed"
