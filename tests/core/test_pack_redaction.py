"""A secret living in a relevant file must never reach the delivered pack.

Locks the invariant after redaction moved from per-candidate reads to the
selected pack items: candidates are read raw for speed, but every DELIVERED item
is redacted.
"""

from __future__ import annotations

from pathlib import Path

from conftest import write_config
from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime

_SECRET = "sk-abcdefghijklmnopqrstuvwxyz123456"


def _runtime_with_secret(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "auth.py").write_text(
        'API_KEY = "' + _SECRET + '"\n\n'
        "def login(user: str) -> bool:\n"
        '    """Authenticate a user against the auth service."""\n'
        "    return bool(user)\n",
        encoding="utf-8",
    )
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project)
    return runtime, project


def test_pack_redacts_secret_from_relevant_file(tmp_path: Path) -> None:
    runtime, _ = _runtime_with_secret(tmp_path)
    pack = runtime.build_context_pack("how does authentication login work")

    included = [getattr(i, "source", "") for i in pack.included]
    assert any("auth.py" in s for s in included), "the relevant file should be retrieved"
    blob = "\n".join(getattr(i, "content", "") for i in pack.included)
    assert _SECRET not in blob, "the secret must be redacted from the delivered pack"


def test_verify_context_redacts_secret(tmp_path: Path) -> None:
    runtime, project = _runtime_with_secret(tmp_path)
    result = runtime.verify_context(
        VerifiedContextRequest(query="authentication login", root=project)
    )
    assert _SECRET not in result.context
    blob = "\n".join(getattr(e, "content", "") for e in result.evidence)
    assert _SECRET not in blob
