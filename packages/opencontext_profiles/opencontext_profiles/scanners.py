"""Framework-specific structural scanners (Workstream F).

Profile scanners surface stack-aware structural signals (Drupal hooks, routes,
services, permissions, plugins) beyond generic symbols. They read files only —
no execution — and degrade quietly on unreadable/malformed files (fail-soft: a
bad file yields no signals, never an exception).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import yaml

from opencontext_core.project.profiles import ProfileSignal

# A Drupal hook implementation: a top-level `function <module>_<hook>(`.
_HOOK_RE = re.compile(r"^function\s+(?P<name>[a-z0-9_]+)\s*\(", re.MULTILINE)
# A PHP class declaration (for src/Plugin/** plugin classes).
_PHP_CLASS_RE = re.compile(
    r"^\s*(?:final\s+|abstract\s+)?class\s+(?P<name>[A-Za-z0-9_]+)", re.MULTILINE
)
# A top-level YAML key (route id, permission, service id) at column 0 — a line
# starting with a non-space, non-comment char, up to its first colon. Drupal
# permission names contain spaces (e.g. "administer mymod"), so the key class
# can't be restricted to word chars.
_YAML_TOP_KEY_RE = re.compile(r"^(?P<key>[^\s#][^:\n]*):", re.MULTILINE)

# Bound the scan so a huge repo can't make this unbounded.
_MAX_FILES = 2000


class DrupalProfileScanner:
    """Surface Drupal structural signals from a project's files.

    Emits :class:`ProfileSignal` for module manifests, hook implementations,
    routes, services, permissions, and plugin classes.
    """

    profile = "drupal"

    def scan(self, project_root: Path, paths: Sequence[str] = ()) -> list[ProfileSignal]:
        path_list = list(paths) if paths else _discover_paths(project_root)
        signals: list[ProfileSignal] = []
        for rel in path_list[:_MAX_FILES]:
            lower = rel.lower()
            if lower.endswith(".info.yml"):
                signals.append(self._manifest_signal(rel))
            elif lower.endswith((".module", ".install", ".theme")):
                signals.extend(self._hook_signals(project_root, rel))
            elif lower.endswith(".routing.yml"):
                signals.extend(self._yaml_key_signals(project_root, rel, "route"))
            elif lower.endswith(".services.yml"):
                signals.extend(self._service_signals(project_root, rel))
            elif lower.endswith(".permissions.yml"):
                signals.extend(self._yaml_key_signals(project_root, rel, "permission"))
            elif "/src/plugin/" in f"/{lower}" and lower.endswith(".php"):
                signals.extend(self._plugin_signals(project_root, rel))
        return signals

    # ── per-kind helpers ──────────────────────────────────────────────────

    def _manifest_signal(self, rel: str) -> ProfileSignal:
        module = Path(rel).name[: -len(".info.yml")]
        return ProfileSignal(
            profile=self.profile,
            kind="manifest",
            name=module,
            file_path=rel,
            line=1,
            detail="Drupal module/theme manifest",
        )

    def _hook_signals(self, root: Path, rel: str) -> list[ProfileSignal]:
        text = _read(root / rel)
        if text is None:
            return []
        out: list[ProfileSignal] = []
        for m in _HOOK_RE.finditer(text):
            out.append(
                ProfileSignal(
                    profile=self.profile,
                    kind="hook",
                    name=m.group("name"),
                    file_path=rel,
                    line=text[: m.start()].count("\n") + 1,
                    detail="hook/function implementation",
                )
            )
        return out

    def _yaml_key_signals(self, root: Path, rel: str, kind: str) -> list[ProfileSignal]:
        text = _read(root / rel)
        if text is None:
            return []
        # Validate it parses as a YAML mapping; if not, fall back to no signals.
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            return []
        if not isinstance(data, dict):
            return []
        out: list[ProfileSignal] = []
        for m in _YAML_TOP_KEY_RE.finditer(text):
            key = m.group("key")
            if key not in data:
                continue
            out.append(
                ProfileSignal(
                    profile=self.profile,
                    kind=kind,
                    name=key,
                    file_path=rel,
                    line=text[: m.start()].count("\n") + 1,
                    detail=f"Drupal {kind} definition",
                )
            )
        return out

    def _service_signals(self, root: Path, rel: str) -> list[ProfileSignal]:
        text = _read(root / rel)
        if text is None:
            return []
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            return []
        services = data.get("services") if isinstance(data, dict) else None
        if not isinstance(services, dict):
            return []
        return [
            ProfileSignal(
                profile=self.profile,
                kind="service",
                name=str(name),
                file_path=rel,
                detail="Drupal service definition",
            )
            for name in services
        ]

    def _plugin_signals(self, root: Path, rel: str) -> list[ProfileSignal]:
        text = _read(root / rel)
        if text is None:
            return []
        out: list[ProfileSignal] = []
        for m in _PHP_CLASS_RE.finditer(text):
            out.append(
                ProfileSignal(
                    profile=self.profile,
                    kind="plugin",
                    name=m.group("name"),
                    file_path=rel,
                    line=text[: m.start()].count("\n") + 1,
                    detail="Drupal plugin class",
                )
            )
        return out


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _discover_paths(project_root: Path) -> list[str]:
    if not project_root.exists():
        return []
    paths: list[str] = []
    for path in project_root.rglob("*"):
        if path.is_file():
            paths.append(path.relative_to(project_root).as_posix())
    return paths
