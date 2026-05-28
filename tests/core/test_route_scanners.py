"""Tests for RouteScanner classes (Django, FastAPI)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.project.profiles import Route, RouteScanner


def _write_py_file(root: Path, rel_path: str, content: str) -> Path:
    """Write a Python file under root, creating parent dirs."""
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return full


class TestRouteModel:
    """Route dataclass basic tests."""

    def test_route_creation(self) -> None:
        route = Route(
            method="GET",
            path="/users/",
            handler="views.user_list",
            file_path="myapp/urls.py",
            line=10,
            framework="django",
        )
        assert route.method == "GET"
        assert route.path == "/users/"
        assert route.handler == "views.user_list"

    def test_route_default_line(self) -> None:
        route = Route(
            method="POST",
            path="/items/",
            handler="items.create",
            file_path="api/routes.py",
            framework="fastapi",
        )
        assert route.line == 0


class TestDjangoRouteScanner:
    """DjangoRouteScanner tests."""

    def _make_scanner(self) -> tuple[RouteScanner, Path]:
        from opencontext_core.project.profiles import DjangoRouteScanner

        return DjangoRouteScanner(), Path("/tmp/_test_django_scan")

    def test_detect_path_routes(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import DjangoRouteScanner

        scanner = DjangoRouteScanner()
        _write_py_file(
            tmp_path,
            "myapp/urls.py",
            (
                "from django.urls import path\n\n"
                "urlpatterns = [\n"
                "    path('users/', views.user_list, name='user-list'),\n"
                "    path('users/<int:pk>/', views.user_detail, name='user-detail'),\n"
                "]\n"
            ),
        )

        routes = scanner.scan(tmp_path)
        assert len(routes) == 2
        assert routes[0].path == "users/"
        assert routes[0].handler == "views.user_list"
        assert routes[0].method == "*"
        assert routes[0].framework == "django"
        assert routes[1].path == "users/<int:pk>/"

    def test_detect_re_path_routes(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import DjangoRouteScanner

        scanner = DjangoRouteScanner()
        _write_py_file(
            tmp_path,
            "api/urls.py",
            (
                "from django.urls import re_path\n\n"
                "urlpatterns = [\n"
                "    re_path(r'^articles/(?P<year>[0-9]{4})/$', views.article_year),\n"
                "]\n"
            ),
        )

        routes = scanner.scan(tmp_path)
        assert len(routes) == 1
        assert routes[0].path.startswith("^articles/")
        assert routes[0].handler == "views.article_year"

    def test_include_is_skipped(self, tmp_path: Path) -> None:
        """Include() calls are not treated as routes."""
        from opencontext_core.project.profiles import DjangoRouteScanner

        scanner = DjangoRouteScanner()
        _write_py_file(
            tmp_path,
            "project/urls.py",
            (
                "from django.urls import include, path\n\n"
                "urlpatterns = [\n"
                "    path('admin/', admin.site.urls),\n"
                "    path('api/', include('api.urls')),\n"
                "    path('users/', views.user_list),\n"
                "]\n"
            ),
        )

        routes = scanner.scan(tmp_path)
        assert len(routes) == 2  # admin and users, NOT include
        # admin.site.urls should be counted as a handler
        assert routes[0].handler == "admin.site.urls"

    def test_empty_urlpatterns(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import DjangoRouteScanner

        scanner = DjangoRouteScanner()
        _write_py_file(
            tmp_path,
            "empty/urls.py",
            "urlpatterns = []\n",
        )

        routes = scanner.scan(tmp_path)
        assert routes == []

    def test_no_urls_file(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import DjangoRouteScanner

        scanner = DjangoRouteScanner()
        routes = scanner.scan(tmp_path)
        assert routes == []


class TestFastAPIRouteScanner:
    """FastAPIRouteScanner tests."""

    def test_detect_get_post_routes(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import FastAPIRouteScanner

        scanner = FastAPIRouteScanner()
        _write_py_file(
            tmp_path,
            "main.py",
            (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/items/')\n"
                "async def list_items():\n"
                "    return []\n\n"
                "@app.post('/items/')\n"
                "def create_item():\n"
                "    pass\n"
            ),
        )

        routes = scanner.scan(tmp_path)
        assert len(routes) == 2
        assert routes[0].method == "GET"
        assert routes[0].path == "/items/"
        assert routes[0].handler == "list_items"
        assert routes[0].framework == "fastapi"
        assert routes[1].method == "POST"
        assert routes[1].handler == "create_item"

    def test_detect_put_delete_routes(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import FastAPIRouteScanner

        scanner = FastAPIRouteScanner()
        _write_py_file(
            tmp_path,
            "app.py",
            (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "@app.put('/items/{item_id}')\n"
                "async def update_item(item_id: int):\n"
                "    pass\n\n"
                "@app.delete('/items/{item_id}')\n"
                "def delete_item(item_id: int):\n"
                "    pass\n"
            ),
        )

        routes = scanner.scan(tmp_path)
        assert len(routes) == 2
        assert routes[0].method == "PUT"
        assert routes[1].method == "DELETE"

    def test_detect_mounted_routers(self, tmp_path: Path) -> None:
        """Sub-routers with prefixes should be detected."""
        from opencontext_core.project.profiles import FastAPIRouteScanner

        scanner = FastAPIRouteScanner()
        _write_py_file(
            tmp_path,
            "routers/users.py",
            (
                "from fastapi import APIRouter\n\n"
                "router = APIRouter(prefix='/users')\n\n"
                "@router.get('/')\n"
                "def list_users():\n"
                "    pass\n\n"
                "@router.get('/{user_id}')\n"
                "def get_user(user_id: int):\n"
                "    pass\n"
            ),
        )

        routes = scanner.scan(tmp_path)
        assert len(routes) == 2
        assert routes[0].path == "/users/"
        assert routes[1].path == "/users/{user_id}"

    def test_no_routes(self, tmp_path: Path) -> None:
        from opencontext_core.project.profiles import FastAPIRouteScanner

        scanner = FastAPIRouteScanner()
        _write_py_file(tmp_path, "empty.py", "x = 1\n")
        routes = scanner.scan(tmp_path)
        assert routes == []
