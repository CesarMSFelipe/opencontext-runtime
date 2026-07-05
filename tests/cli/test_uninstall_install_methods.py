"""Uninstall reports HOW the package is installed — report-only, never residue.

Config removal does not uninstall the pipx/pip/zipapp distribution; that is the
package manager's job. So ``uninstall --verify`` must *surface* the install
method with the right uninstall command, but must never count it as residue
(which would make verify fail on every machine that can run the code).
"""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.commands.uninstall_cmd import _detect_install_methods


def test_detect_install_methods_shape() -> None:
    methods = _detect_install_methods()
    # Running this test means the package IS installed by some method.
    assert isinstance(methods, list)
    for m in methods:
        assert set(m) == {"method", "location", "hint"}
        assert m["method"] in {"pipx", "pip", "editable", "zipapp"}
        assert m["hint"]


def test_pipx_detected_when_venv_present(monkeypatch, tmp_path: Path) -> None:
    fake_home = tmp_path
    venv = fake_home / ".local" / "share" / "pipx" / "venvs" / "opencontext-cli"
    venv.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    methods = _detect_install_methods()
    pipx = [m for m in methods if m["method"] == "pipx"]
    assert pipx, f"pipx venv present but not reported: {methods}"
    assert pipx[0]["hint"] == "pipx uninstall opencontext-cli"


def test_install_methods_never_counted_as_residue(monkeypatch, tmp_path: Path) -> None:
    """The advisory must not leak into the residue lists that decide `passed`."""
    from opencontext_cli.commands.uninstall_cmd import verify_no_global_traces

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # A clean HOME → no residue, regardless of how the package is installed.
    assert verify_no_global_traces([]) == []
