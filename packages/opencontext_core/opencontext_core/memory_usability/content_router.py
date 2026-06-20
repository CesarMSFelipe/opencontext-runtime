"""Route content to safe compression and serialization policies."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.memory_usability.serializers import SerializationFormat
from opencontext_core.models.context import ContentFormat


class ContentType(StrEnum):
    """Content categories understood by the memory/token usability layer."""

    CODE = "code"
    LOGS = "logs"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    TRACE = "trace"
    TOOL_OUTPUT = "tool_output"
    MEMORY_FACT = "memory_fact"
    REPO_MAP = "repo_map"
    SECURITY_FINDING = "security_finding"
    WORKFLOW = "workflow"
    PLAIN_TEXT = "plain_text"
    UNKNOWN = "unknown"


class ContentRoute(BaseModel):
    """Routing decision for one content payload."""

    model_config = ConfigDict(extra="forbid")

    content_type: ContentType = Field(description="Detected content type.")
    content_format: ContentFormat = Field(
        default=ContentFormat.UNKNOWN,
        description="Structural format of the content (prose/code/json/shell).",
    )
    compression_strategy: str = Field(description="Compression strategy key.")
    serialization_format: SerializationFormat = Field(description="Preferred serializer.")
    protected_spans: list[str] = Field(description="Protected span kinds.")
    security_policy: str = Field(description="Security policy name.")
    untrusted: bool = Field(default=True, description="Whether content must be wrapped as data.")


class ContentRouter:
    """Deterministically routes content by extension, structure, and source role."""

    def route(
        self,
        content: str,
        *,
        path: str | None = None,
        declared_type: ContentType | None = None,
    ) -> ContentRoute:
        """Return a safe route for content."""

        content_type = declared_type or self.detect(content, path=path)
        content_format = self.detect_format(content, content_type=content_type)

        routes: dict[ContentType, tuple[str, SerializationFormat, list[str], str, bool]] = {
            ContentType.CODE: (
                "code_ast",
                SerializationFormat.MARKDOWN,
                ["code", "paths", "symbols", "numbers"],
                "no_lossy_in_act_or_implement",
                True,
            ),
            ContentType.LOGS: (
                "head_tail_error_focused",
                SerializationFormat.COMPACT_TABLE,
                ["timestamps", "errors", "paths", "numbers"],
                "redact_tool_output",
                True,
            ),
            ContentType.JSON: (
                "smart_crusher",
                SerializationFormat.JSON,
                ["keys", "numbers"],
                "redact_values",
                True,
            ),
            ContentType.YAML: (
                "structural_prune",
                SerializationFormat.TOON,
                ["keys", "numbers"],
                "redact_values",
                True,
            ),
            ContentType.TOOL_OUTPUT: (
                "tool_output_prune",
                SerializationFormat.MARKDOWN,
                ["errors", "commands", "paths"],
                "wrap_untrusted_redact",
                True,
            ),
            ContentType.REPO_MAP: (
                "repo_map_compact",
                SerializationFormat.TOON,
                ["paths", "symbols"],
                "no_raw_source",
                True,
            ),
            ContentType.SECURITY_FINDING: (
                "structured_finding",
                SerializationFormat.COMPACT_TABLE,
                ["fingerprints", "classifications"],
                "no_raw_secret",
                True,
            ),
        }
        # Override strategy based on structural format when applicable
        strategy_override: dict[ContentFormat, str] = {
            ContentFormat.JSON_ARRAY: "smart_crusher",
            ContentFormat.CODE: "code_ast",
            ContentFormat.SHELL_OUTPUT: "extractive_head_tail",
            ContentFormat.PROSE: "terse",
        }
        strategy = routes.get(content_type, (None, None, None, None, None))[0]
        if strategy is None:
            strategy = "extractive_head_tail"
        strategy = strategy_override.get(content_format, strategy)

        default = routes.get(
            content_type,
            (
                strategy,
                SerializationFormat.MARKDOWN,
                ["paths", "numbers"],
                "redact",
                True,
            ),
        )
        return ContentRoute(
            content_type=content_type,
            content_format=content_format,
            compression_strategy=default[0],
            serialization_format=default[1],
            protected_spans=default[2],
            security_policy=default[3],
            untrusted=default[4],
        )

    def detect(self, content: str, *, path: str | None = None) -> ContentType:
        """Detect content type from path and basic structure."""

        suffix = Path(path or "").suffix.lower()
        if suffix in {".py", ".ts", ".js", ".php", ".go", ".rs", ".cs", ".java"}:
            return ContentType.CODE
        if suffix in {".json"}:
            return ContentType.JSON
        if suffix in {".yaml", ".yml"}:
            return ContentType.YAML
        if suffix in {".md", ".rst"}:
            return ContentType.MARKDOWN
        if suffix in {".log"}:
            return ContentType.LOGS
        if _looks_like_json(content):
            return ContentType.JSON
        if "trace_id" in content and "span_id" in content:
            return ContentType.TRACE
        if "SECURITY" in content or "secret" in content.lower():
            return ContentType.SECURITY_FINDING
        return ContentType.PLAIN_TEXT if content.strip() else ContentType.UNKNOWN

    def detect_format(
        self, content: str, *, content_type: ContentType | None = None
    ) -> ContentFormat:
        """Detect structural format of the content.

        This goes beyond the content-type classification to determine the
        *structural shape* of the text — useful for selecting the right
        compression backend.

        Returns one of ContentFormat (PROSE, CODE, JSON_ARRAY, SHELL_OUTPUT, etc.)
        """
        if not content.strip():
            return ContentFormat.UNKNOWN

        if content_type == ContentType.CODE:
            return ContentFormat.CODE

        if content_type == ContentType.JSON:
            if _json_is_array(content):
                return ContentFormat.JSON_ARRAY
            return ContentFormat.JSON_STRUCTURED

        if _looks_like_json(content):
            if _json_is_array(content):
                return ContentFormat.JSON_ARRAY
            return ContentFormat.JSON_STRUCTURED

        if _looks_like_shell_output(content):
            return ContentFormat.SHELL_OUTPUT

        if _looks_like_code(content):
            return ContentFormat.CODE

        if _looks_like_markdown(content):
            return ContentFormat.MARKDOWN

        return ContentFormat.PROSE


# ── Structural heuristics ────────────────────────────────────────────────


def _looks_like_json(content: str) -> bool:
    stripped = content.strip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _json_is_array(content: str) -> bool:
    stripped = content.strip()
    if not stripped.startswith("["):
        return False
    try:
        data = json.loads(stripped)
        return isinstance(data, list) and len(data) >= 2
    except (json.JSONDecodeError, ValueError):
        return False


def _looks_like_shell_output(content: str) -> bool:
    """Detect shell/output content by common patterns."""
    stripped = content.strip()
    lines = stripped.splitlines()[:20]
    shell_indicators = 0
    for line in lines:
        if line.startswith(("$ ", "> ", "❯ ")):  # noqa: RUF001 — literal prompt glyph, intentional
            shell_indicators += 1
        elif re.match(r"^(?:\./|/|[a-zA-Z]:\\)", line):
            shell_indicators += 1
        elif re.match(r"^(?:error|warning|fatal|traceback)", line, re.I):
            shell_indicators += 1
        elif re.match(r"^\d+:\d+", line):  # timestamps
            shell_indicators += 1
    # If >30% of lines look like shell output
    return shell_indicators > max(1, len(lines) * 0.3)


def _looks_like_code(content: str) -> bool:
    """Detect source code by indentation, keywords, and structure."""
    stripped = content.strip()
    lines = stripped.splitlines()
    if len(lines) < 3:
        return False

    indicators = 0
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith(("def ", "class ", "import ", "from ", "fn ", "pub ", "func ")):
            indicators += 2
        elif s.endswith((":", "->", "=>", "{", "}")):
            indicators += 1
        elif re.match(r"^\s+", line):  # indented line
            indicators += 1
        elif re.match(r"^\S+\s*=\s*", s):  # assignment
            indicators += 1

    # If >40% of non-empty lines look like code
    non_empty = sum(1 for line in lines if line.strip())
    return non_empty > 0 and indicators > non_empty * 0.4


def _looks_like_markdown(content: str) -> bool:
    """Detect Markdown by common block elements."""
    lines = content.strip().splitlines()
    md_indicators = 0
    for line in lines[:30]:
        s = line.strip()
        if s.startswith(("# ", "## ", "### ", "> ", "- ", "* ", "1. ")):
            md_indicators += 1
        elif s.startswith("```"):
            md_indicators += 2
        elif re.match(r"^\[.+\]\(.+\)", s):  # [text](url)
            md_indicators += 1
    return md_indicators >= 3
