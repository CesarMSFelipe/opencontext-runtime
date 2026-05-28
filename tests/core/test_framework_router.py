"""Tests for FrameworkRouter — framework-aware route detection."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from opencontext_core.indexing.framework_router import FrameworkRouter, RouteDefinition


def _write_file(root: Path, rel_path: str, content: str) -> Path:
    """Write a source file under root."""
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


class TestFrameworkRouter:
    def test_detect_fastapi_get_route(self, tmp_path: Path) -> None:
        """FastAPI GET decorator is correctly detected."""
        _write_file(
            tmp_path,
            "main.py",
            (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/users')\n"
                "def list_users():\n"
                "    return []\n"
            ),
        )
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) == 1
        route = routes[0]
        assert route.framework == "fastapi"
        assert route.method == "GET"
        assert route.path_pattern == "/users"

    def test_detect_django_path(self, tmp_path: Path) -> None:
        """Django path() calls are detected."""
        _write_file(
            tmp_path,
            "urls.py",
            (
                "from django.urls import path, include\n\n"
                "urlpatterns = [\n"
                "    path('admin/', admin.site.urls),\n"
                "]\n"
            ),
        )
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) >= 1
        route = routes[0]
        assert route.framework == "django"
        assert route.path_pattern == "admin/"
        assert route.method == "ANY"

    def test_detect_flask_route(self, tmp_path: Path) -> None:
        """Flask @app.route() decorator is detected."""
        _write_file(
            tmp_path,
            "app.py",
            (
                "from flask import Flask\n\n"
                "app = Flask(__name__)\n\n"
                "@app.route('/health')\n"
                "def health_check():\n"
                "    return 'ok'\n"
            ),
        )
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) == 1
        route = routes[0]
        assert route.framework == "flask"
        assert route.path_pattern == "/health"
        assert route.method == "ANY"

    def test_detect_express_route(self, tmp_path: Path) -> None:
        """Express.js app.get() call in a .js file is detected."""
        _write_file(
            tmp_path,
            "server.js",
            (
                "const express = require('express');\n"
                "const app = express();\n\n"
                "app.get('/api/users', handler);\n"
            ),
        )
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) == 1
        route = routes[0]
        assert route.framework == "express"
        assert route.method == "GET"
        assert route.path_pattern == "/api/users"

    def test_detect_nestjs_decorator(self, tmp_path: Path) -> None:
        """NestJS @Get() decorator in a .ts file is detected."""
        _write_file(
            tmp_path,
            "items.controller.ts",
            (
                "import { Controller, Get } from '@nestjs/common';\n\n"
                "@Controller('items')\n"
                "export class ItemsController {\n"
                "  @Get('/items')\n"
                "  findAll() {\n"
                "    return [];\n"
                "  }\n"
                "}\n"
            ),
        )
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) >= 1
        # Find the GET route
        get_routes = [r for r in routes if r.method == "GET" and r.framework == "nestjs"]
        assert len(get_routes) >= 1
        assert get_routes[0].path_pattern == "/items"

    def test_no_routes_in_empty_file(self, tmp_path: Path) -> None:
        """A pure Python file with no decorators returns no routes."""
        _write_file(tmp_path, "utils.py", ("def helper(x):\n    return x * 2\n\nCONSTANT = 42\n"))
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert routes == []

    def test_routes_sorted_by_file(self, tmp_path: Path) -> None:
        """Multiple routes from multiple files are all collected."""
        _write_file(
            tmp_path,
            "api/users.py",
            (
                "from fastapi import APIRouter\n\n"
                "router = APIRouter()\n\n"
                "@router.get('/users')\n"
                "def list_users(): pass\n"
            ),
        )
        _write_file(
            tmp_path,
            "api/items.py",
            (
                "from fastapi import APIRouter\n\n"
                "router = APIRouter()\n\n"
                "@router.post('/items')\n"
                "def create_item(): pass\n"
            ),
        )
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) == 2
        frameworks = {r.framework for r in routes}
        assert frameworks == {"fastapi"}
        methods = {r.method for r in routes}
        assert "GET" in methods
        assert "POST" in methods

    def test_scan_returns_routedefinition_dataclass(self, tmp_path: Path) -> None:
        """Verify RouteDefinition has expected fields: source_file, framework, method, path_pattern, line."""
        _write_file(tmp_path, "views.py", ("@app.get('/ping')\ndef ping(): pass\n"))
        router = FrameworkRouter()
        routes = router.scan(tmp_path)
        assert len(routes) == 1
        route = routes[0]
        assert isinstance(route, RouteDefinition)
        # Verify all required fields exist
        assert hasattr(route, "source_file")
        assert hasattr(route, "framework")
        assert hasattr(route, "method")
        assert hasattr(route, "path_pattern")
        assert hasattr(route, "line")
        assert route.line > 0
        assert route.source_file.endswith("views.py")
        # Verify it is a dataclass
        assert dataclasses.is_dataclass(route)
