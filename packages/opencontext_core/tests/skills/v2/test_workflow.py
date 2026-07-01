"""Tests for skills.v2.workflow — dry-run + YAML manifest parsing."""

from __future__ import annotations

from opencontext_core.skills.v2.workflow import WorkflowManifest, dry_run, load_manifest


def test_dry_run_no_side_effects() -> None:
    """dry_run returns the planned step list without executing anything."""
    manifest = WorkflowManifest(
        id="wf-1",
        steps=["step.a", "step.b", "step.c"],
    )
    planned = dry_run(manifest)
    assert planned == ["step.a", "step.b", "step.c"]
    # no side effects: manifest unchanged, no run tree
    assert manifest.steps == ["step.a", "step.b", "step.c"]


def test_from_yaml_parses_manifest() -> None:
    """load_manifest parses a YAML manifest into a WorkflowManifest."""
    import textwrap

    yaml_blob = textwrap.dedent(
        """
        id: oc-flow
        steps:
          - apply.diff
          - verify.checks
        """
    ).strip()
    manifest = load_manifest(yaml_blob)
    assert isinstance(manifest, WorkflowManifest)
    assert manifest.id == "oc-flow"
    assert manifest.steps == ["apply.diff", "verify.checks"]
