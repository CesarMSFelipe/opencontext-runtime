from __future__ import annotations

import json
from pathlib import Path

from opencontext_cli.main import _inspect, _provider_simulate, _security, _tokens, _trace
from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.packing import sanitize_context_pack
from opencontext_core.models.context import ContextItem, ContextPackResult, ContextPriority
from opencontext_core.retrieval.ranking import RetrievalScorer
from opencontext_core.runtime import OpenContextRuntime
from opencontext_core.safety.firewall import ContextFirewall
from opencontext_core.safety.secrets import SecretScanner
from tests.core.conftest import create_sample_project, write_config


def test_secret_findings_are_fingerprint_only() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    findings = SecretScanner().scan_secret_findings(f"OPENAI_API_KEY={secret}")

    assert findings
    assert findings[0].kind in {"openai_api_key", "env_secret"}
    assert secret not in findings[0].model_dump_json()
    assert findings[0].redacted_value.startswith("[REDACTED:")


def test_context_firewall_redacts_raw_secret_export() -> None:
    config = default_config_data()
    firewall = ContextFirewall(OpenContextConfig.model_validate(config))
    item = ContextItem(
        id="secret",
        content="token sk-abcdefghijklmnopqrstuvwxyz123456",
        source=".env",
        source_type="file",
        priority=ContextPriority.P1,
        tokens=10,
        score=1.0,
    )

    decision = firewall.check_context_export([item], sink="test")

    # Redact-and-continue: a local export sanitizes in place instead of hard-failing,
    # so a benign secret-like fixture no longer breaks `pack`. The raw value is gone.
    assert decision.allowed is True
    assert item.redacted is True
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in item.content
    assert any("redacted_secrets" in w for w in decision.warnings)


def test_sanitized_pack_passes_context_firewall() -> None:
    config = default_config_data()
    firewall = ContextFirewall(OpenContextConfig.model_validate(config))
    pack = ContextPackResult(
        included=[
            ContextItem(
                id="secret",
                content="token sk-abcdefghijklmnopqrstuvwxyz123456",
                source=".env",
                source_type="file",
                priority=ContextPriority.P1,
                tokens=10,
                score=1.0,
            )
        ],
        omitted=[],
        used_tokens=10,
        available_tokens=100,
        omissions=[],
    )

    sanitized = sanitize_context_pack(pack)
    decision = firewall.check_context_export(sanitized.included, sink="test")

    assert decision.allowed is True
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in sanitized.included[0].content


def test_pack_persists_local_only_sanitized_trace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    runtime.index_project(project_root)
    pack = runtime.build_context_pack("authentication", max_tokens=1000)
    trace = runtime.latest_trace()

    assert pack.used_tokens <= 1000
    assert trace.provider == "local-only"
    assert trace.token_estimates["provider_calls"] == 0
    assert {"project.retrieve", "context.rank", "context.pack", "prompt.assemble"} <= {
        span.name for span in trace.spans
    }
    assert all(item.content == "[REDACTED]" for item in trace.selected_context_items)
    metadata_items = trace.metadata["context_pack"]["included"]
    assert metadata_items
    assert all(item["content"] == "[REDACTED]" for item in metadata_items)


def test_cli_output_flags_write_proof_artifacts(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config_path = write_config(tmp_path, project_root)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")
    runtime.index_project(project_root)
    runtime.build_context_pack("authentication", max_tokens=1000)

    token_output = tmp_path / "tokens.json"
    security_output = tmp_path / "security.json"
    repomap_output = tmp_path / "repomap.txt"
    trace_output = tmp_path / "trace.json"

    _tokens("report", project_root, 5, str(token_output))
    _security("scan", str(project_root), output_path=str(security_output))
    _inspect(runtime, "repomap", max_tokens=500, output_path=str(repomap_output))
    _trace(runtime, "last", output_path=str(trace_output))

    capsys.readouterr()
    assert token_output.exists()
    assert security_output.exists()
    assert repomap_output.exists()
    assert trace_output.exists()
    assert json.loads(token_output.read_text(encoding="utf-8"))["baseline_indexable_files"] > 0
    assert "auth.py" in repomap_output.read_text(encoding="utf-8")


def test_provider_simulate_allows_local_secret_policy(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_path = write_config(tmp_path, project_root)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")

    _provider_simulate("local", "secret", runtime)

    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["allowed"] is True


def test_query_stopwords_do_not_dominate_context_retrieval() -> None:
    terms = RetrievalScorer().terms("How does context packing work in this project?")

    assert terms == ["context", "packing", "pack"]
