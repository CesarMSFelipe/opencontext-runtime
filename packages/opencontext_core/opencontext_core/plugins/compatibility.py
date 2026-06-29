"""Plugin version-compatibility enforcement (PR-015, book §12 Compatibility).

``min_core_version`` was parsed but never compared (KEY DISCOVERY 2). This module
wires the comparison: a plugin declares ``requires.runtime`` (e.g. ``>=2.0``) and
optionally a legacy ``min_core_version``; both are checked against the running
runtime version. An incompatible plugin stays discovered-but-disabled with a
recorded reason — the lifecycle stops before activation.

Dependency-free semver comparison (no ``packaging`` dependency): versions are
compared as zero-padded integer tuples, which is sufficient for the ``X.Y.Z``
scheme the runtime and registry use.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.plugins.manifest import PluginManifest

_OPERATORS = (">=", "<=", "==", "~=", "!=", ">", "<", "=")


@dataclass(frozen=True)
class CompatResult:
    """Outcome of a compatibility check."""

    ok: bool
    reason: str


def _parse_version(value: str) -> tuple[int, ...]:
    """Parse ``X.Y.Z`` (tolerant of a leading ``v`` and non-numeric suffixes)."""
    cleaned = value.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """Three-way compare two version tuples, zero-padded to equal length."""
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return (a > b) - (a < b)


def _split_spec(spec: str) -> tuple[str, str]:
    """Split a spec like ``>=2.0`` into ``(operator, version)``.

    A bare version (no operator) is treated as ``>=`` (the floor convention used
    by ``min_core_version``).
    """
    spec = spec.strip()
    for op in _OPERATORS:
        if spec.startswith(op):
            return op, spec[len(op) :].strip()
    return ">=", spec


def _satisfies(core_version: str, spec: str) -> bool:
    """Return True when ``core_version`` satisfies a single ``spec`` clause."""
    if not spec.strip():
        return True
    op, want = _split_spec(spec)
    c = _cmp(_parse_version(core_version), _parse_version(want))
    if op in (">=",):
        return c >= 0
    if op == ">":
        return c > 0
    if op == "<=":
        return c <= 0
    if op == "<":
        return c < 0
    if op in ("==", "="):
        return c == 0
    if op == "!=":
        return c != 0
    if op == "~=":
        # Compatible release: same major, >= the requested minor/patch.
        want_parts = _parse_version(want)
        core_parts = _parse_version(core_version)
        if want_parts and core_parts and want_parts[0] != core_parts[0]:
            return False
        return c >= 0
    return False


def check_compatibility(
    manifest: PluginManifest,
    core_version: str,
    *,
    min_core_version: str | None = None,
) -> CompatResult:
    """Check a plugin's declared requirements against the running runtime.

    Evaluates ``manifest.requires.runtime`` and the optional legacy
    ``min_core_version`` (from the registry entry). Both must hold. Returns a
    :class:`CompatResult`; an incompatible plugin yields a stable reason the
    lifecycle records as ``status="incompatible"``.
    """
    runtime_spec = manifest.requires.runtime
    if runtime_spec and not _satisfies(core_version, runtime_spec):
        return CompatResult(
            ok=False,
            reason=f"requires runtime {runtime_spec}, core is {core_version}",
        )
    if min_core_version and not _satisfies(core_version, f">={min_core_version}"):
        return CompatResult(
            ok=False,
            reason=f"requires min_core_version {min_core_version}, core is {core_version}",
        )
    return CompatResult(ok=True, reason="compatible")


def runtime_version() -> str:
    """Best-effort running runtime version (``opencontext-core`` package)."""
    import importlib.metadata

    for pkg in ("opencontext-core", "opencontext-cli"):
        try:
            return importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "0.0.0"
