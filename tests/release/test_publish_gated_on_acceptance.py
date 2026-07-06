"""RELEASE_CONTRACT: no publish unless the installed product passes acceptance.

publish.yml must run release-acceptance.yml as a reusable workflow in the same
run (same ref, so tag publishes are gated on the tag's commit) and the PyPI
upload job must declare it as a `needs:` prerequisite. release-acceptance.yml
stays usable standalone via its own triggers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PUBLISH_YML = REPO / ".github" / "workflows" / "publish.yml"
ACCEPTANCE_YML = REPO / ".github" / "workflows" / "release-acceptance.yml"

ACCEPTANCE_PATH = ".github/workflows/release-acceptance.yml"


@pytest.fixture(scope="module")
def publish_doc() -> dict[str, Any]:
    assert PUBLISH_YML.is_file(), "publish.yml is missing"
    return yaml.safe_load(PUBLISH_YML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def acceptance_doc() -> dict[str, Any]:
    assert ACCEPTANCE_YML.is_file(), "release-acceptance.yml is missing"
    return yaml.safe_load(ACCEPTANCE_YML.read_text(encoding="utf-8"))


def _triggers(doc: dict[str, Any]) -> dict[str, Any]:
    # YAML 1.1 parses a bare `on` key as boolean True.
    return doc.get("on") or doc.get(True) or {}


def _gate_jobs(publish_doc: dict[str, Any]) -> list[str]:
    return [
        name
        for name, job in publish_doc["jobs"].items()
        if str((job or {}).get("uses", "")).endswith(ACCEPTANCE_PATH)
    ]


def test_release_acceptance_is_callable_and_standalone(acceptance_doc: dict[str, Any]) -> None:
    triggers = _triggers(acceptance_doc)
    assert "workflow_call" in triggers, "release-acceptance.yml must expose workflow_call"
    assert "workflow_dispatch" in triggers, "release-acceptance.yml must stay runnable standalone"


def test_publish_calls_release_acceptance_in_same_run(publish_doc: dict[str, Any]) -> None:
    assert _gate_jobs(publish_doc), "publish.yml must call release-acceptance.yml via uses:"


def test_publish_upload_needs_the_acceptance_gate(publish_doc: dict[str, Any]) -> None:
    gate_jobs = set(_gate_jobs(publish_doc))
    publish_job = publish_doc["jobs"]["build-and-publish"]
    needs = publish_job.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    assert gate_jobs and gate_jobs <= set(needs), (
        "build-and-publish must declare needs: on the release-acceptance gate job"
    )


def test_acceptance_covers_the_contract_stages() -> None:
    """The gate publish depends on must include hygiene, fresh-venv install,
    acceptance against the installed binary, and uninstall-verify."""
    text = ACCEPTANCE_YML.read_text(encoding="utf-8")
    assert "audit_release_artifacts.py" in text  # artifact hygiene audit (AC-029)
    assert "pip install -q packages/*/dist/*.whl" in text  # fresh-venv install (AC-030)
    assert "--oc-bin" in text  # acceptance runs against the installed product
    assert "uninstall --scope workspace --purge --verify" in text  # uninstall verify
