from __future__ import annotations

from pathlib import Path

from conftest import write_config
from opencontext_core.runtime import OpenContextRuntime
from opencontext_core.safety.secrets import SecretScanner


def test_secret_scanner_redacts_common_patterns() -> None:
    _openai = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    _github = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
    text = "\n".join(
        [
            f"OPENAI_API_KEY={_openai}",
            f"GITHUB_TOKEN={_github}",
            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
            "safe text remains",
        ]
    )

    redacted = SecretScanner().redact(text)

    assert _openai not in redacted
    assert _github not in redacted
    assert "-----BEGIN PRIVATE KEY-----" not in redacted
    assert "safe text remains" in redacted


def test_secret_scanner_covers_enterprise_patterns_without_raw_findings() -> None:
    _anthropic = "sk-ant-api03-" + "abcdefghijklmnopqrstuvwxyz123456"
    _slack = "xoxb" + "-123456789012-mock-slack-token-12345"
    _google = "AIza" + "0123456789abcdef0123456789abcdef012"
    _stripe = "sk_" + "test_0123456789abcdef012345"
    text = "\n".join(
        [
            f"ANTHROPIC_API_KEY={_anthropic}",
            "DATABASE_URL=postgres://user:pass@example.com/db",
            f"SLACK_TOKEN={_slack}",
            f"GOOGLE_API_KEY={_google}",
            f"STRIPE_SECRET_KEY={_stripe}",
            "JWT=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmnop.qrstuvwxyz123456",
        ]
    )

    scanner = SecretScanner()
    findings = scanner.scan(text)
    redacted = scanner.redact(text)
    kinds = {finding.kind for finding in findings}

    assert "anthropic_api_key" in kinds
    assert "database_url" in kinds
    assert "slack_token" in kinds
    assert "google_api_key" in kinds
    assert "stripe_key" in kinds
    assert "jwt_like_token" in kinds
    assert all(finding.value == "[REDACTED]" for finding in findings)
    assert "postgres://user:pass@example.com/db" not in redacted


def test_secret_files_not_included_raw_in_prompt_context(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    (project / ".env").write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
    config_path = write_config(tmp_path, project)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")

    manifest = runtime.index_project(project)
    result = runtime.ask("OPENAI_API_KEY")
    trace = runtime.load_trace(result.trace_id)

    assert manifest.metadata["safety"]["files_with_potential_secrets"] == [".env"]
    assert secret not in "\n".join(item.content for item in trace.selected_context_items)
    assert secret not in trace.final_answer
    assembled_prompt = "\n".join(section.content for section in trace.prompt_sections)
    assert secret not in assembled_prompt


def test_prompt_sink_guard_redacts_pii_and_secret(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    (project / "notes.txt").write_text(
        f"email admin@example.com token {secret}",
        encoding="utf-8",
    )
    config_path = write_config(tmp_path, project)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")
    runtime.index_project(project)
    result = runtime.ask("Find sensitive entries")
    trace = runtime.load_trace(result.trace_id)
    rendered_prompt = "\n".join(section.content for section in trace.prompt_sections)
    assert "admin@example.com" not in rendered_prompt
    assert secret not in rendered_prompt


def test_manifest_persistence_redacts_sensitive_summaries(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "leak.txt").write_text("admin@example.com", encoding="utf-8")
    config_path = write_config(tmp_path, project)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")
    manifest = runtime.index_project(project)
    leaked_before = [f for f in manifest.files if "@" in f.summary]
    assert leaked_before
    persisted = runtime.load_manifest()
    assert all("@" not in file.summary for file in persisted.files)
