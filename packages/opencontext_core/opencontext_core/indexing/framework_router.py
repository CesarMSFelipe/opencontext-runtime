"""Framework-aware route detection — maps URL patterns to handler functions.

Supports Django, FastAPI, Flask, Express.js, and NestJS.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RouteDefinition:
    source_file: str
    framework: str  # django | fastapi | flask | express | nestjs
    method: str  # GET | POST | PUT | DELETE | ANY | *
    path_pattern: str
    handler: str  # function/class name detected
    line: int = 0


_SKIP_DIRS = frozenset(
    {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build"}
)
_SOURCE_EXTENSIONS = frozenset({".py", ".ts", ".tsx", ".js", ".jsx"})

_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # Django urlpatterns: path('route/', view_func)  or  url(r'^route/', view_func)
    (re.compile(r"(?:path|re_path|url)\s*\(\s*['\"]([^'\"]*)['\"].*?,\s*(\w+)"), "django", "ANY"),
    # FastAPI decorators: @app.get('/'), @router.post('/')
    (
        re.compile(r"@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]"),
        "fastapi",
        "",
    ),
    # Flask: @app.route('/'), @bp.route('/')
    (re.compile(r"@(?:app|bp|blueprint)\s*\.\s*route\s*\(\s*['\"]([^'\"]+)['\"]"), "flask", "ANY"),
    # Express: app.get('/route', handler) or router.post('/route', handler)
    (
        re.compile(r"(?:app|router)\.(get|post|put|delete|patch|all)\s*\(\s*['\"]([^'\"]+)['\"]"),
        "express",
        "",
    ),
    # NestJS: @Get('/'), @Post('/')
    (re.compile(r"@(Get|Post|Put|Delete|Patch)\s*\(\s*['\"]([^'\"]*)['\"]"), "nestjs", ""),
]


class FrameworkRouter:
    def scan(self, root: str | Path = ".") -> list[RouteDefinition]:
        root_path = Path(root).resolve()
        routes: list[RouteDefinition] = []
        for file_path in self._iter_source_files(root_path):
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            routes.extend(self._scan_file(file_path, content, root_path))
        return routes

    def _scan_file(self, file_path: Path, content: str, root: Path) -> list[RouteDefinition]:
        found: list[RouteDefinition] = []
        rel_path = file_path.relative_to(root).as_posix()
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            for pattern, framework, _default_method in _PATTERNS:
                m = pattern.search(line)
                if not m:
                    continue
                groups = m.groups()
                if framework == "django":
                    path_pat, handler = groups[0], groups[1] if len(groups) > 1 else ""
                    method = "ANY"
                elif framework in ("fastapi", "express"):
                    method, path_pat = groups[0].upper(), groups[1] if len(groups) > 1 else ""
                    handler = ""
                elif framework == "nestjs":
                    method, path_pat = groups[0].upper(), groups[1] if len(groups) > 1 else ""
                    handler = ""
                else:  # flask
                    path_pat, method, handler = groups[0], "ANY", ""
                found.append(
                    RouteDefinition(
                        source_file=rel_path,
                        framework=framework,
                        method=method,
                        path_pattern=path_pat,
                        handler=handler,
                        line=i,
                    )
                )
                break
        return found

    def _iter_source_files(self, root: Path) -> Iterator[Path]:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in _SOURCE_EXTENSIONS:
                if not any(part in _SKIP_DIRS for part in path.parts):
                    yield path
