"""commit-020: AST guard — Studio must consume public contracts only.

Walking every ``.py`` file under :mod:`opencontext_studio`'s source tree,
any import that resolves to a private path of ``opencontext_core.*`` —
or to a public symbol NOT in the allowlist — fails the gate with a
precise list of offending imports.

The allowlist mirrors SPEC STUDIO-A7: Studio may only depend on the
public API surface of the core runtime. Adding a new internal
dependency in Studio without first exposing it on the public contract
is the regression this test blocks.
"""

from __future__ import annotations

import ast
from pathlib import Path

STUDIO_SRC = Path("packages/opencontext_studio/opencontext_studio")
PUBLIC_CONTRACT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "opencontext_core.runtime.api",
        "opencontext_core.session.store",
        "opencontext_core.artifacts.store",
        "opencontext_core.receipts.store",
        "opencontext_core.decision_log",
        "opencontext_core.kg.reader",
        "opencontext_core.memory.reader",
        # studio-serving-consolidation: StudioReader is the sanctioned read
        # contract for all v2 endpoint data, and core redaction (SinkGuard via
        # redact_value) is the single redaction path applied at the response
        # boundary. Both are deliberate public-contract additions.
        "opencontext_core.studio.reader",
        "opencontext_core.studio.redaction",
    }
)


def _collect_offending_imports() -> list[tuple[Path, str, int, str]]:
    """Walk Studio's source tree and return offending import statements."""
    if not STUDIO_SRC.exists():
        return []
    offenders: list[tuple[Path, str, int, str]] = []
    for py_file in sorted(STUDIO_SRC.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - syntax errors surface elsewhere
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if not node.module.startswith("opencontext_core"):
                    continue
                if node.module in PUBLIC_CONTRACT_ALLOWLIST:
                    continue
                target = node.module
                in_allowlist = target in PUBLIC_CONTRACT_ALLOWLIST or any(
                    target == allowed or target.startswith(allowed + ".")
                    for allowed in PUBLIC_CONTRACT_ALLOWLIST
                )
                if in_allowlist:
                    continue
                offenders.append(
                    (py_file, node.module, node.lineno, ",".join(a.name for a in node.names))
                )
    return offenders


def test_studio_imports_only_public_contracts() -> None:
    offending = _collect_offending_imports()
    if offending:
        formatted = "\n".join(
            f"  {path}:{line}  `{module}`  (imports {names})"
            for path, module, line, names in offending
        )
        raise AssertionError(
            "opencontext_studio must only import from the public contract allowlist:\n"
            + formatted
        )
