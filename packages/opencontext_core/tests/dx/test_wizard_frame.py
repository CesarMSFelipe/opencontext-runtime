"""Wizard frame chrome must match the config TUI aspect (one brand, one layout)."""

from __future__ import annotations

from opencontext_core.dx.wizard_frame import WizardStep, frame_lines


def _joined(lines: list[str]) -> str:
    return "\n".join(lines)


def test_frame_uses_canonical_product_title() -> None:
    # The config TUI BrandBar titles every screen "OpenContext Runtime";
    # the wizard frame must carry the same product name.
    lines = frame_lines(1, 3, WizardStep(title="Example"), "status")
    assert "OpenContext Runtime" in _joined(lines)


def test_frame_carries_status_line_and_progress() -> None:
    step = WizardStep(
        title="Example",
        current="a",
        effect="b",
        recommended="c",
        risk="d",
        cli="e",
    )
    text = _joined(frame_lines(2, 4, step, "proj · installed · KG: ok"))
    assert "proj · installed · KG: ok" in text
    assert "Step 2/4" in text
    assert "Current:" in text
    assert "Effect:" in text
    assert "Recommended:" in text
    assert "Risk / note:" in text
    assert "CLI:" in text


def test_frame_skips_empty_card_fields() -> None:
    text = _joined(frame_lines(1, 1, WizardStep(title="Bare", effect="only effect")))
    assert "Effect:" in text
    assert "Current:" not in text
    assert "CLI:" not in text
