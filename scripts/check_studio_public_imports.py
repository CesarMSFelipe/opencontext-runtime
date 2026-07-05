#!/usr/bin/env python3
"""commit-020: AST guard for Studio's public-contract imports.

CLI parity with ``packages/opencontext_studio/tests/server/test_public_contract_imports.py``.
Run in CI to fail builds when Studio starts importing private internals
of ``opencontext_core``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the test module importable when this script is run as `python scripts/...`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "opencontext_studio" / "tests" / "server"))

from test_public_contract_imports import _collect_offending_imports  # noqa: E402


def main() -> int:
    offending = _collect_offending_imports()
    if not offending:
        print("opencontext_studio: public-contract gate OK")
        return 0
    print("opencontext_studio: public-contract gate FAILED", file=sys.stderr)
    for path, module, line, names in offending:
        print(f"  {path}:{line}  `{module}`  (imports {names})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
