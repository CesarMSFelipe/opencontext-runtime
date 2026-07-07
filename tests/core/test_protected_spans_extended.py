"""CTX-PROTECTED-LIST tests: protected-span detectors for the DOC2 §13.4 list.

Covers the previously missing categories — imports, relevant configuration,
memory/KG-referenced fragments, recent changes (diff fragments), and recent
decisions — plus the documented default decision for signature protection.
"""

from __future__ import annotations

from opencontext_core.context.protection import ProtectedSpanManager


def _kinds(spans) -> set[str]:
    return {span.kind for span in spans}


def test_import_lines_are_protected_spans() -> None:
    """CTX-PROTECTED-LIST: imports (DOC2 §13.4) — Python, JS, require, #include
    and Rust use lines are detected as protected ``import`` spans."""
    manager = ProtectedSpanManager()
    content = "\n".join(
        [
            "from pathlib import Path",
            "import os",
            "import { login } from './auth'",
            "const fs = require('fs')",
            "#include <stdio.h>",
            "use std::collections::HashMap;",
            "some prose that is compressible and not an import at all",
        ]
    )
    spans = [s for s in manager.detect(content, include_semantic=True) if s.kind == "import"]
    detected = " ".join(span.content for span in spans)
    assert "from pathlib import Path" in detected
    assert "import os" in detected
    assert "require('fs')" in detected
    assert "#include <stdio.h>" in detected
    assert "use std::collections::HashMap;" in detected


def test_relevant_configuration_is_protected() -> None:
    """CTX-PROTECTED-LIST: relevant configuration (DOC2 §13.4 'configuración
    relevante') — env-style assignments and ini/toml section headers are detected
    as protected ``configuration`` spans."""
    manager = ProtectedSpanManager()
    content = "\n".join(
        [
            "MAX_RETRIES=3",
            "export DATABASE_URL: postgres://localhost/app",
            "[tool.opencontext]",
            "regular sentence without any effective configuration",
        ]
    )
    spans = [s for s in manager.detect_semantic_keep(content) if s.kind == "configuration"]
    detected = " ".join(span.content for span in spans)
    assert "MAX_RETRIES=3" in detected
    assert "DATABASE_URL" in detected
    assert "[tool.opencontext]" in detected

    # On the combined detect() path the env assignment keeps the configuration
    # kind; the bracketed header stays protected too (the pre-existing citation
    # detector wins the overlap dedupe there, which is equally load-bearing).
    combined = manager.detect(content, include_semantic=True)
    assert "configuration" in _kinds(combined)
    assert any("[tool.opencontext]" in span.content for span in combined)


def test_recent_change_diff_fragments_are_protected() -> None:
    """CTX-PROTECTED-LIST: recent changes (DOC2 §13.4 'cambios recientes') —
    unified-diff fragments (diff/index/hunk headers) are detected as protected
    ``recent_change`` spans."""
    manager = ProtectedSpanManager()
    content = "\n".join(
        [
            "diff --git a/src/auth.py b/src/auth.py",
            "index 3f9a2b1..8c4d5e6 100644",
            "--- a/src/auth.py",
            "+++ b/src/auth.py",
            "@@ -10,6 +10,7 @@ class AuthService:",
        ]
    )
    spans = manager.detect(content, include_semantic=True)
    assert "recent_change" in _kinds(spans)
    detected = " ".join(s.content for s in spans if s.kind == "recent_change")
    assert "diff --git" in detected
    assert "@@ -10,6 +10,7 @@" in detected


def test_recent_decisions_are_protected() -> None:
    """CTX-PROTECTED-LIST: recent decisions (DOC1 'decisiones recientes') —
    decision/ADR marker lines are detected as protected ``recent_decision``
    spans."""
    manager = ProtectedSpanManager()
    content = "\n".join(
        [
            "## Decision: keep the hexagonal core",
            "ADR-012 accepted after review",
            "we talked about lunch, nothing binding here",
        ]
    )
    spans = [
        s for s in manager.detect(content, include_semantic=True) if s.kind == "recent_decision"
    ]
    detected = " ".join(span.content for span in spans)
    assert "Decision: keep the hexagonal core" in detected
    assert "ADR-012" in detected


def test_memory_and_kg_referenced_fragments_are_protected() -> None:
    """CTX-PROTECTED-LIST: fragments referenced by memory or KG (DOC2 §13.4) —
    caller-supplied referenced fragments are detected as protected
    ``referenced_fragment`` spans wherever they occur in the content."""
    manager = ProtectedSpanManager()
    content = (
        "The handler validates tokens.\n"
        "audit_login records every attempt.\n"
        "Unrelated compressible narrative follows here.\n"
    )
    spans = manager.detect_referenced_fragments(content, ["audit_login", "zz"])
    assert spans, "referenced fragments must produce protected spans"
    assert all(span.kind == "referenced_fragment" for span in spans)
    assert spans[0].content == "audit_login"

    # The same references flow through detect() as an additive opt-in argument.
    combined = manager.detect(content, referenced_fragments=["audit_login"])
    assert "referenced_fragment" in _kinds(combined)


def test_new_detectors_stay_out_of_the_legacy_default_path() -> None:
    """CTX-PROTECTED-LIST: documented default decision — the new detectors (and
    signature protection) stay OPT-IN via ``include_semantic``: the legacy
    default ``detect()`` output is byte-compatible (no import/configuration/
    recent_change/recent_decision/signature kinds), because the legacy engine's
    unchanged behavior is a pinned compatibility contract
    (test_legacy_compression_unchanged_without_semantic_protection); the v2
    Context Engine path (semantic_protection=True) is the DOC2 §13.4 surface."""
    manager = ProtectedSpanManager()
    content = "\n".join(
        [
            "import os",
            "MAX_RETRIES=3",
            "diff --git a/x b/x",
            "## Decision: something",
            "def login(user):",
        ]
    )
    legacy_kinds = _kinds(manager.detect(content))
    for kind in ("import", "configuration", "recent_change", "recent_decision", "signature"):
        assert kind not in legacy_kinds, f"{kind} must remain opt-in (semantic path only)"
    semantic_kinds = _kinds(manager.detect(content, include_semantic=True))
    for kind in ("import", "configuration", "recent_change", "recent_decision", "signature"):
        assert kind in semantic_kinds, f"{kind} must be detected on the semantic path"
