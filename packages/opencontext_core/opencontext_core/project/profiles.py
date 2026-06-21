"""Technology profile interfaces that keep core framework-agnostic."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.models.project import FileKind, ProjectFile, Symbol

GENERIC_PROFILE = "generic"


class Route(BaseModel):
    """A detected HTTP route in a project."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(description="HTTP method (GET, POST, etc.) or '*' for any.")
    path: str = Field(description="URL path pattern (e.g. '/users/<id>').")
    handler: str = Field(description="Handler function or class name.")
    file_path: str = Field(description="Project-relative file path.")
    line: int = Field(default=0, description="Line number in source file.")
    framework: str = Field(description="Framework identifier (django, fastapi, etc.).")


class RouteScanner(Protocol):
    """Protocol for framework-specific route scanners."""

    framework: str

    def scan(self, project_root: Path, paths: Sequence[str] = ()) -> list[Route]:
        """Scan project files and return detected routes."""


class ProfileDetectionResult(BaseModel):
    """Detection result emitted by a technology profile."""

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(description="Stable technology profile identifier.")
    score: float = Field(ge=0.0, le=1.0, description="Detection confidence.")
    markers: list[str] = Field(
        default_factory=list,
        description="Project-relative markers that contributed to detection.",
    )


class FileClassificationResult(BaseModel):
    """Profile-specific file classification hint."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Project-relative path.")
    kind: FileKind = Field(description="Suggested high-level file kind.")
    tags: list[str] = Field(default_factory=list, description="Profile-specific tags.")


class ContextProviderReference(BaseModel):
    """Reference to a context provider contributed by a profile."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Provider key.")
    description: str = Field(description="Provider purpose.")


class WorkflowPackReference(BaseModel):
    """Reference to a workflow pack suggested by a profile."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Workflow pack name.")
    mode: str = Field(description="Recommended context mode.")


class SafeCommand(BaseModel):
    """Profile-suggested command that still requires runtime policy approval."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Command identifier.")
    command: tuple[str, ...] = Field(description="Executable and arguments.")
    read_only: bool = Field(default=True, description="Whether the command is expected read-only.")
    network: bool = Field(default=False, description="Whether the command needs network access.")


class TechnologyProfile(Protocol):
    """Optional stack-specific intelligence plugged into the universal core."""

    name: str

    def detect(
        self,
        project_root: Path,
        paths: Sequence[str] = (),
    ) -> ProfileDetectionResult:
        """Detect this technology profile for a project."""

    def classify_file(self, path: Path) -> FileClassificationResult | None:
        """Return a profile-specific classification hint for one path."""

    def extract_symbols(self, file: ProjectFile) -> list[Symbol]:
        """Return extra profile-specific symbols beyond the core extractor."""

    def build_context_providers(self) -> list[ContextProviderReference]:
        """Return context providers exposed by this profile."""

    def suggest_workflows(self) -> list[WorkflowPackReference]:
        """Return workflow packs suggested by this profile."""

    def suggest_validation_commands(self) -> list[SafeCommand]:
        """Return validation command suggestions, never direct execution."""


class GenericTechnologyProfile:
    """Fallback profile for projects without specialized first-party profiles."""

    name = GENERIC_PROFILE

    def detect(
        self,
        project_root: Path,
        paths: Sequence[str] = (),
    ) -> ProfileDetectionResult:
        """Return a generic detection result."""

        markers = ["no technology-specific profile required"] if paths else []
        return ProfileDetectionResult(profile=self.name, score=1.0, markers=markers)

    def classify_file(self, path: Path) -> FileClassificationResult | None:
        """Generic profile does not override core file classification."""

        return None

    def extract_symbols(self, file: ProjectFile) -> list[Symbol]:
        """Generic profile does not add symbols beyond core extraction."""

        return []

    def build_context_providers(self) -> list[ContextProviderReference]:
        """Generic profile does not add specialized context providers."""

        return []

    def suggest_workflows(self) -> list[WorkflowPackReference]:
        """Return universal workflow suggestions."""

        return [
            WorkflowPackReference(name="code-review", mode="review"),
            WorkflowPackReference(name="security-audit", mode="audit"),
        ]

    def suggest_validation_commands(self) -> list[SafeCommand]:
        """Generic profile does not suggest executable validation commands."""

        return []


# ── Route Scanners ──────────────────────────────────────────────────────────


class DjangoRouteScanner:
    """Scan Django ``urls.py`` files for ``path()`` and ``re_path()`` routes."""

    framework = "django"

    def scan(self, project_root: Path, paths: Sequence[str] = ()) -> list[Route]:
        """Scan Python files named ``urls.py`` for Django route definitions.

        Detects ``path(route, view, ...)`` and ``re_path(route, view, ...)``
        calls inside ``urlpatterns`` lists.  ``include()`` calls are skipped.
        """
        routes: list[Route] = []

        # Determine which files to scan
        if paths:
            url_files = [p for p in paths if p.endswith("urls.py")]
        else:
            url_files = self._find_urls_files(project_root)

        for rel_path in url_files:
            full_path = project_root / rel_path
            if not full_path.is_file():
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            routes.extend(self._scan_content(rel_path, content))

        return routes

    def _find_urls_files(self, root: Path) -> list[str]:
        """Walk the project tree and find ``urls.py`` files."""
        import os

        results: list[str] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if fn == "urls.py":
                    full = Path(dirpath) / fn
                    try:
                        results.append(full.relative_to(root).as_posix())
                    except ValueError:
                        continue
        return results

    def _scan_content(self, rel_path: str, content: str) -> list[Route]:
        """Extract routes from a single ``urls.py`` file."""
        import re

        routes: list[Route] = []

        # Match: path('...', view_func, ...)  or  re_path(r'...', view_func, ...)
        # Handles r'', f'', b'', and plain string prefixes
        pattern = re.compile(
            r"(?:path|re_path)\s*\(\s*"
            r"(?:[rRfFuUbB]*)?"
            r"['\"](?P<route>[^'\"]+)['\"]\s*,\s*"
            r"(?P<view>[^,)]+?)"
            r"(?:\s*[,)])",
        )

        for match in pattern.finditer(content):
            route_str = match.group("route")
            view_str = match.group("view").strip()

            # Skip include() calls
            if view_str.startswith("include("):
                continue

            routes.append(
                Route(
                    method="*",
                    path=route_str,
                    handler=view_str,
                    file_path=rel_path,
                    line=content[: match.start()].count("\n") + 1,
                    framework=self.framework,
                )
            )

        return routes


class FastAPIRouteScanner:
    """Scan FastAPI files for ``@app.get()``, ``@router.post()``, etc. routes."""

    framework = "fastapi"

    def scan(self, project_root: Path, paths: Sequence[str] = ()) -> list[Route]:
        """Scan Python files for FastAPI route decorators.

        Detects ``@<instance>.<method>(<path>)`` patterns where instance
        is an ``app`` or ``router`` variable, and method is an HTTP verb
        (get, post, put, patch, delete).
        """
        import os

        routes: list[Route] = []

        py_files: list[str] = []
        if paths:
            py_files = [p for p in paths if p.endswith(".py")]
        else:
            for dirpath, _dirnames, filenames in os.walk(project_root):
                for fn in filenames:
                    if fn.endswith(".py"):
                        full = Path(dirpath) / fn
                        try:
                            py_files.append(full.relative_to(project_root).as_posix())
                        except ValueError:
                            continue

        for rel_path in py_files:
            full_path = project_root / rel_path
            if not full_path.is_file():
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            routes.extend(self._scan_content(rel_path, content))

        return routes

    def _scan_content(self, rel_path: str, content: str) -> list[Route]:
        """Extract routes from a single Python file."""
        import re

        routes: list[Route] = []

        # Match: @app.get('...'), @router.post("..."), etc.
        # Also handles multi-line: @app.get(  '...'  )
        pattern = re.compile(
            r"@(?P<instance>\w+)\s*\.\s*(?P<method>get|post|put|patch|delete|options|head)\s*"
            r"\(\s*"
            r"['\"](?P<path>[^'\"]+)['\"]",
        )

        # Track APIRouter instances with prefixes
        prefixes: dict[str, str] = {}
        prefix_pattern = re.compile(
            r"(?P<var>\w+)\s*=\s*APIRouter\s*\(.*?prefix\s*=\s*['\"](?P<prefix>[^'\"]+)['\"]",
        )
        for p_match in prefix_pattern.finditer(content):
            prefixes[p_match.group("var")] = p_match.group("prefix")

        for match in pattern.finditer(content):
            instance = match.group("instance")
            method = match.group("method").upper()
            path = match.group("path")

            # Resolve handler name: the next function/method def after the decorator
            handler = self._resolve_handler(content, match.end())

            # Apply prefix if the instance is an APIRouter
            if instance in prefixes:
                prefix = prefixes[instance].rstrip("/")
                if not path.startswith("/"):
                    path = "/" + path
                path = prefix + path

            routes.append(
                Route(
                    method=method,
                    path=path,
                    handler=handler or f"{instance}.{method.lower()}",
                    file_path=rel_path,
                    line=content[: match.start()].count("\n") + 1,
                    framework=self.framework,
                )
            )

        return routes

    @staticmethod
    def _resolve_handler(content: str, decorator_end: int) -> str:
        """Find the function name after a decorator."""
        import re

        rest = content[decorator_end:]
        # Skip whitespace and find the next def/async def
        func_match = re.search(
            r"^\s*(?:async\s+)?def\s+(?P<name>\w+)\s*\(",
            rest,
            re.MULTILINE,
        )
        if func_match:
            return func_match.group("name")
        return ""


# ── Scanner registry ────────────────────────────────────────────────────────

_FRAMEWORK_SCANNERS: dict[str, type[RouteScanner]] = {}


def register_scanner(framework: str, scanner_cls: type[RouteScanner]) -> None:
    """Register a route scanner for a framework.

    Called automatically by importing scanner modules.
    """
    _FRAMEWORK_SCANNERS[framework] = scanner_cls


def scanners_for_profiles(profiles: list[str]) -> list[RouteScanner]:
    """Return route scanner instances for the given profile names."""
    scanners: list[RouteScanner] = []
    for profile_name in profiles:
        if profile_name in _FRAMEWORK_SCANNERS:
            scanners.append(_FRAMEWORK_SCANNERS[profile_name]())
    return scanners


# Register built-in scanners
register_scanner("django", DjangoRouteScanner)
register_scanner("fastapi", FastAPIRouteScanner)
