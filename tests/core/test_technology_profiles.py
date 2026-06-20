from __future__ import annotations

from pathlib import Path

from opencontext_core.config import ProjectIndexConfig
from opencontext_core.indexing.project_indexer import ProjectIndexer
from opencontext_core.models.project import ProjectManifest
from opencontext_profiles import first_party_profiles


def test_core_project_indexer_is_generic_without_first_party_profiles(tmp_path: Path) -> None:
    (tmp_path / "example.info.yml").write_text("name: Example\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "generic-only").build_manifest()

    assert manifest.profile == "generic"
    assert manifest.technology_profiles == ["generic"]
    assert manifest.frameworks == ["generic"]


def test_first_party_profiles_detect_multiple_stacks(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("export function App() { return null; }\n")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(
        config,
        "node-project",
        profiles=first_party_profiles(),
    ).build_manifest()

    assert "node" in manifest.technology_profiles
    assert "python" not in manifest.technology_profiles
    assert manifest.profile == "node"


def test_dominant_code_language_wins_without_markers(tmp_path: Path) -> None:
    # Loose source files with no manifest markers: the dominant code language wins
    # (2 python files vs 1 js), not whatever language detector scores on the js.
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "loose-py", profiles=first_party_profiles()).build_manifest()

    assert manifest.profile == "python"


def test_first_party_profile_registry_suggests_safe_commands() -> None:
    profiles = {profile.name: profile for profile in first_party_profiles()}
    python_commands = profiles["python"].suggest_validation_commands()

    assert "drupal" in profiles
    assert "terraform" in profiles
    assert "angular" in profiles
    assert "docker" in profiles
    assert "kubernetes" in profiles
    assert "dbt" in profiles
    assert "salesforce" in profiles
    assert "opentelemetry" in profiles
    assert "hardhat" in profiles
    assert "godot" in profiles
    assert "uv" in profiles
    assert len(profiles) >= 220
    assert python_commands
    assert all(command.read_only for command in python_commands)
    assert all(not command.network for command in python_commands)


def test_additional_profiles_detect_representative_stacks(tmp_path: Path) -> None:
    fixtures = {
        "angular": ("angular.json", "{}\n"),
        "docker": ("Dockerfile", "FROM python:3.12\n"),
        "dbt": ("dbt_project.yml", "name: analytics\n"),
        "swift": ("Package.swift", "// swift-tools-version: 5.10\n"),
        "prisma": ("schema.prisma", 'datasource db { provider = "postgresql" }\n'),
        "opentelemetry": ("otelcol.yaml", "receivers: {}\n"),
        "hardhat": ("hardhat.config.ts", "export default {}\n"),
        "godot": ("project.godot", "[application]\n"),
        "uv": ("uv.lock", "version = 1\n"),
        "openapi": ("openapi.yaml", "openapi: 3.1.0\n"),
    }
    profiles = first_party_profiles()
    for expected_profile, (relative_path, content) in fixtures.items():
        project_root = tmp_path / expected_profile
        file_path = project_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        manifest = ProjectIndexer(
            ProjectIndexConfig(root=str(project_root), profile="generic", ignore=[]),
            expected_profile,
            profiles=profiles,
        ).build_manifest()

        assert expected_profile in manifest.technology_profiles


def test_project_manifest_loads_legacy_frameworks_key() -> None:
    manifest = ProjectManifest.model_validate(
        {
            "project_name": "legacy",
            "root": "/tmp/legacy",
            "profile": "drupal",
            "frameworks": ["drupal"],
            "files": [],
            "symbols": [],
            "generated_at": "2026-05-02T00:00:00Z",
            "metadata": {},
        }
    )

    assert manifest.technology_profiles == ["drupal"]
    assert manifest.frameworks == ["drupal"]
    assert "technology_profiles" in manifest.model_dump()
    assert "frameworks" not in manifest.model_dump()


def test_core_python_sources_do_not_contain_first_party_profile_logic() -> None:
    core_root = Path(__file__).parents[2] / "packages/opencontext_core/opencontext_core"
    forbidden = ("drupal", "symfony", "laravel", "wordpress", "django", "fastapi")
    # Framework route detection legitimately references framework names
    excluded = {
        "indexing/framework_routes.py",  # route parser for django/fastapi/flask
        "indexing/framework_router.py",  # router detection, sibling to framework_routes
        "evaluation/comparative.py",  # benchmark tasks use framework names as test data
        "workflow/extension_registry.py",  # extension registry lists framework-related extensions
        "project/profiles.py",  # technology profile detection checks framework names
    }
    offenders: list[str] = []
    for path in core_root.rglob("*.py"):
        rel = path.relative_to(core_root).as_posix()
        if rel in excluded:
            continue
        text = path.read_text(encoding="utf-8").lower()
        if any(term in text for term in forbidden):
            offenders.append(rel)

    assert offenders == []
