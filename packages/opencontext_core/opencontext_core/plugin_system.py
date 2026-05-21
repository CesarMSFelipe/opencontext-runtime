"""Plugin system for OpenContext.

Extensible plugin architecture:
- Plugin discovery, loading, lifecycle
- Remote plugin registry with built-in fallback
- GitHub releases and direct URL installation
- Auto-update with version checks
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/"
    "opencontext/plugin-registry/main/registry.json"
)

PLUGIN_CACHE_DURATION = timedelta(hours=1)
UPDATE_CACHE_DURATION = timedelta(hours=24)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class PluginInfo:
    """Information about an installed plugin."""

    name: str
    version: str
    description: str
    author: str = ""
    entry_point: str = "plugin.py"
    hooks: list[str] = field(default_factory=list)
    enabled: bool = True

    # Install source tracking
    homepage: str = ""
    repository: str = ""
    install_source: str = "local"  # local | registry | github | url
    source_url: str = ""           # registry URL, GitHub repo, or download URL
    installed_at: str = ""
    updated_at: str = ""


@dataclass
class RegistryPlugin:
    """A plugin entry in the remote registry."""

    name: str
    description: str
    author: str = ""
    homepage: str = ""
    repository: str = ""
    versions: list[RegistryVersion] = field(default_factory=list)


@dataclass
class RegistryVersion:
    """A specific version of a registry plugin."""

    version: str
    min_core_version: str = "0.1.0"
    download_url: str = ""
    checksum: str = ""  # sha256:hex


@dataclass
class InstallResult:
    """Result of a plugin installation."""

    name: str
    version: str
    status: str  # installed | updated | skipped | failed
    message: str = ""
    error: str = ""
    source: str = ""


# ── Base Plugin Class ──────────────────────────────────────────────────────

class Plugin(ABC):
    """Base class for OpenContext plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    def initialize(self, context: dict[str, Any]) -> None:
        """Called when plugin is loaded."""
        pass

    def shutdown(self) -> None:
        """Called when plugin is unloaded."""
        pass

    def register_commands(self, registry: Any) -> None:
        """Register CLI commands."""
        pass

    def register_hooks(self, registry: Any) -> None:
        """Register hooks."""
        pass


# ── Built-in Registry Data ─────────────────────────────────────────────────

_BUILTIN_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "security-audit",
        "description": "Security audit and vulnerability scanning for OpenContext projects",
        "author": "OpenContext Team",
        "homepage": "https://github.com/opencontext/plugin-security-audit",
        "repository": "https://github.com/opencontext/plugin-security-audit",
        "versions": [
            {
                "version": "0.1.0",
                "min_core_version": "0.1.0",
                "download_url": "",
                "checksum": "",
            }
        ],
    },
    {
        "name": "performance",
        "description": "Performance profiling, bottleneck detection, and optimization suggestions",
        "author": "OpenContext Team",
        "homepage": "https://github.com/opencontext/plugin-performance",
        "repository": "https://github.com/opencontext/plugin-performance",
        "versions": [
            {
                "version": "0.1.0",
                "min_core_version": "0.1.0",
                "download_url": "",
                "checksum": "",
            }
        ],
    },
    {
        "name": "team",
        "description": "Team collaboration tools, shared conventions, and peer review workflows",
        "author": "OpenContext Team",
        "homepage": "https://github.com/opencontext/plugin-team",
        "repository": "https://github.com/opencontext/plugin-team",
        "versions": [
            {
                "version": "0.1.0",
                "min_core_version": "0.1.0",
                "download_url": "",
                "checksum": "",
            }
        ],
    },
]


# ── Registry Fetcher ───────────────────────────────────────────────────────

class RegistryFetcher:
    """Fetches and caches the remote plugin registry."""

    CACHE_FILE = Path.home() / ".config" / "opencontext" / "registry-cache.json"

    def __init__(self, registry_url: str = DEFAULT_REGISTRY_URL) -> None:
        self.registry_url = registry_url

    def fetch(self, force: bool = False) -> list[RegistryPlugin]:
        """Fetch registry, with fallback to built-in.

        Tries remote first, falls back to built-in if unreachable.
        Caches remote results for 1 hour.
        """

        # If forced, skip cache
        if not force:
            cached = self._load_cache()
            if cached is not None:
                return cached

        # Try remote
        try:
            req = Request(self.registry_url, headers={"User-Agent": "OpenContext/1.0"})
            with urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode())
                plugins = self._parse(raw)
                self._save_cache(plugins)
                return plugins
        except Exception:
            pass

        # Fallback: cached if we have it
        cached = self._load_cache()
        if cached is not None:
            return cached

        # Final fallback: built-in
        return self._parse_builtin()

    def search(self, query: str = "", force: bool = False) -> list[RegistryPlugin]:
        """Search registry for plugins matching query."""

        plugins = self.fetch(force=force)
        if not query:
            return plugins

        q = query.lower()
        results = []
        for p in plugins:
            if (
                q in p.name.lower()
                or q in p.description.lower()
                or q in p.author.lower()
            ):
                results.append(p)
        return results

    def get(self, name: str) -> RegistryPlugin | None:
        """Get a specific plugin by name."""

        for p in self.fetch():
            if p.name == name:
                return p
        return None

    def _parse(self, raw: Any) -> list[RegistryPlugin]:
        """Parse raw registry JSON."""

        entries = raw if isinstance(raw, list) else raw.get("plugins", [])
        plugins = []
        for entry in entries:
            versions = []
            for v in entry.get("versions", []):
                versions.append(
                    RegistryVersion(
                        version=v["version"],
                        min_core_version=v.get("min_core_version", "0.1.0"),
                        download_url=v.get("download_url", ""),
                        checksum=v.get("checksum", ""),
                    )
                )
            plugins.append(
                RegistryPlugin(
                    name=entry["name"],
                    description=entry.get("description", ""),
                    author=entry.get("author", ""),
                    homepage=entry.get("homepage", ""),
                    repository=entry.get("repository", ""),
                    versions=versions,
                )
            )
        return plugins

    def _parse_builtin(self) -> list[RegistryPlugin]:
        """Parse built-in registry entries."""

        return self._parse(_BUILTIN_REGISTRY)

    def _load_cache(self) -> list[RegistryPlugin] | None:
        """Load cached registry, returns None if expired."""

        if not self.CACHE_FILE.exists():
            return None
        try:
            data = json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
            cached_at = data.get("cached_at", "")
            if cached_at:
                age = datetime.now() - datetime.fromisoformat(cached_at)
                if age < PLUGIN_CACHE_DURATION:
                    return self._parse(data.get("plugins", []))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return None

    def _save_cache(self, plugins: list[RegistryPlugin]) -> None:
        """Save registry to cache."""

        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cached_at": datetime.now().isoformat(),
            "plugins": [
                {
                    "name": p.name,
                    "description": p.description,
                    "author": p.author,
                    "homepage": p.homepage,
                    "repository": p.repository,
                    "versions": [
                        {
                            "version": v.version,
                            "min_core_version": v.min_core_version,
                            "download_url": v.download_url,
                            "checksum": v.checksum,
                        }
                        for v in p.versions
                    ],
                }
                for p in plugins
            ],
        }
        self.CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Plugin Installer ───────────────────────────────────────────────────────

class PluginInstaller:
    """Installs plugins from various sources."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry or PluginRegistry()

    def install_from_registry(
        self, name: str, version: str | None = None,
    ) -> InstallResult:
        """Install a plugin from the remote registry."""

        fetcher = RegistryFetcher()
        entry = fetcher.get(name)
        if entry is None:
            return InstallResult(
                name=name, version="",
                status="failed",
                message=f"Plugin '{name}' not found in registry",
            )

        # Pick version
        if version:
            # User explicitly requested a version — must match exactly
            ver_info = self._find_exact_version(entry, version)
            if ver_info is None:
                available = ", ".join(v.version for v in entry.versions)
                return InstallResult(
                    name=name, version=version,
                    status="failed",
                    message=f"Version '{version}' not available for '{name}' — available: {available}",
                )
            target_version = version
        else:
            # No version specified — use latest
            ver_info = entry.versions[0] if entry.versions else None
            if ver_info is None:
                return InstallResult(
                    name=name, version="",
                    status="failed",
                    message=f"No versions available for '{name}'",
                )
            target_version = ver_info.version

        # Already installed?
        existing = self.registry.get_info(name)
        if existing and existing.version == target_version:
            return InstallResult(
                name=name, version=target_version,
                status="skipped",
                message=f"'{name}' v{target_version} already installed",
            )

        if ver_info.download_url:
            return self._install_from_url(
                name=name,
                version=target_version,
                url=ver_info.download_url,
                checksum=ver_info.checksum,
                install_source="registry",
                source_url=entry.repository or "",
                homepage=entry.homepage,
                description=entry.description,
                author=entry.author,
            )
        else:
            # No download URL — scaffold plugin stub
            return self._install_stub(
                name=name,
                version=target_version,
                description=entry.description,
                author=entry.author,
                homepage=entry.homepage,
                repository=entry.repository,
                install_source="registry",
            )

    def install_from_github(
        self, repo: str, name: str | None = None,
    ) -> InstallResult:
        """Install a plugin from a GitHub repository.

        Args:
            repo: GitHub repo in 'owner/repo' format.
            name: Plugin name. Defaults to repo name.
        """

        # Normalize repo
        repo = repo.strip().rstrip("/")
        if repo.startswith("https://github.com/"):
            repo = repo[len("https://github.com/"):]
        if repo.startswith("github.com/"):
            repo = repo[len("github.com/"):]
        if repo.endswith(".git"):
            repo = repo[:-4]

        parts = repo.split("/")
        if len(parts) < 2:
            return InstallResult(
                name=repo, version="",
                status="failed",
                message=f"Invalid GitHub repo format: '{repo}'. Use 'owner/repo'.",
            )

        owner, repo_name = parts[0], parts[1]
        plugin_name = name or repo_name

        # Fetch latest release via GitHub API
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
        try:
            req = Request(api_url, headers={"User-Agent": "OpenContext/1.0", "Accept": "application/vnd.github.v3+json"})
            with urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read().decode())

            tag = release.get("tag_name", "").lstrip("v")
            # Find the right asset (zip or tar.gz)
            assets = release.get("assets", [])
            download_url = ""
            for asset in assets:
                name_lower = asset["name"].lower()
                if name_lower.endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break
                elif name_lower.endswith(".tar.gz") and not download_url:
                    download_url = asset["browser_download_url"]

            if not download_url:
                # Fallback: download source archive
                download_url = f"https://github.com/{owner}/{repo_name}/archive/refs/tags/{release['tag_name']}.tar.gz"

            return self._install_from_url(
                name=plugin_name,
                version=tag,
                url=download_url,
                install_source="github",
                source_url=f"https://github.com/{owner}/{repo_name}",
                homepage=f"https://github.com/{owner}/{repo_name}",
                description=release.get("body", "").split("\n")[0] if release.get("body") else f"Plugin from {owner}/{repo_name}",
                author=owner,
            )
        except Exception as e:
            # Fallback: try archive download without API
            return self._install_from_github_archive(
                owner=owner, repo_name=repo_name,
                plugin_name=plugin_name,
            )

    def install_from_url(self, name: str, url: str) -> InstallResult:
        """Install a plugin from a direct download URL."""

        return self._install_from_url(
            name=name,
            version="0.1.0",
            url=url,
            install_source="url",
            source_url=url,
        )

    def _install_from_github_archive(
        self, owner: str, repo_name: str, plugin_name: str,
    ) -> InstallResult:
        """Fallback: download GitHub archive without API."""

        # Try to guess the latest tag or use main branch
        archive_url = (
            f"https://github.com/{owner}/{repo_name}/archive/refs/heads/main.zip"
        )
        try:
            req = Request(archive_url)
            with urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise ValueError("Archive not found")
            # We can reach it, install it
            return self._install_from_url(
                name=plugin_name,
                version="main",
                url=archive_url,
                install_source="github",
                source_url=f"https://github.com/{owner}/{repo_name}",
                description=f"Plugin from {owner}/{repo_name} (main branch)",
                author=owner,
            )
        except Exception as e:
            return InstallResult(
                name=plugin_name, version="",
                status="failed",
                message=f"Could not download from {owner}/{repo_name}: {e}",
                source=f"https://github.com/{owner}/{repo_name}",
            )

    def _install_from_url(
        self,
        name: str,
        version: str,
        url: str,
        checksum: str = "",
        install_source: str = "url",
        source_url: str = "",
        homepage: str = "",
        description: str = "",
        author: str = "",
    ) -> InstallResult:
        """Download and install a plugin from a URL."""

        # Already installed at this version?
        existing = self.registry.get_info(name)
        if existing and existing.version == version and existing.source_url == source_url:
            return InstallResult(
                name=name, version=version,
                status="skipped",
                message=f"'{name}' v{version} already installed from same source",
            )

        plugin_dir = self.registry.plugins_dir / name

        try:
            # Create temp download
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name
                req = Request(url, headers={"User-Agent": "OpenContext/1.0"})
                with urlopen(req, timeout=30) as resp:
                    tmp.write(resp.read())

            # Verify checksum if provided
            if checksum and checksum.startswith("sha256:"):
                import hashlib
                expected = checksum[len("sha256:"):]
                actual = hashlib.sha256(Path(tmp_path).read_bytes()).hexdigest()
                if actual != expected:
                    Path(tmp_path).unlink(missing_ok=True)
                    return InstallResult(
                        name=name, version=version,
                        status="failed",
                        message="Checksum mismatch — download may be corrupted",
                    )

            # Back up existing if any
            if plugin_dir.exists():
                backup_dir = plugin_dir.parent / f".{name}.bak"
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.copytree(plugin_dir, backup_dir)

            # Extract
            plugin_dir.mkdir(parents=True, exist_ok=True)
            if zipfile.is_zipfile(tmp_path):
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    # Handle top-level directory in archive
                    members = zf.namelist()
                    top_level = _get_top_level_dir(members)
                    if top_level:
                        for member in members:
                            if member == top_level or member.startswith(top_level):
                                rel = member[len(top_level):].lstrip("/")
                                if not rel:
                                    continue
                                target = plugin_dir / rel
                                if member.endswith("/"):
                                    target.mkdir(parents=True, exist_ok=True)
                                else:
                                    target.parent.mkdir(parents=True, exist_ok=True)
                                    target.write_bytes(zf.read(member))
                    else:
                        zf.extractall(str(plugin_dir))
            else:
                # Assume tar.gz
                import tarfile
                with tarfile.open(tmp_path, "r:*") as tf:
                    tf.extractall(str(plugin_dir))

            Path(tmp_path).unlink(missing_ok=True)

            # Ensure plugin.json exists
            manifest_path = plugin_dir / "plugin.json"
            if not manifest_path.exists():
                manifest = {
                    "name": name,
                    "version": version,
                    "description": description or f"Plugin '{name}'",
                    "author": author or "Unknown",
                    "entry_point": "plugin.py",
                    "hooks": [],
                    "enabled": True,
                    "homepage": homepage,
                    "repository": source_url,
                    "install_source": install_source,
                    "source_url": source_url,
                    "installed_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                manifest_path.write_text(
                    json.dumps(manifest, indent=2), encoding="utf-8"
                )
            else:
                # Update existing manifest
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["version"] = version
                    manifest["updated_at"] = datetime.now().isoformat()
                    manifest["install_source"] = install_source
                    manifest["source_url"] = source_url
                    if homepage:
                        manifest["homepage"] = homepage
                    if description:
                        manifest["description"] = description
                    if author:
                        manifest["author"] = author
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2), encoding="utf-8"
                    )
                except (json.JSONDecodeError, OSError):
                    pass

            # Remove backup on success
            backup_dir = plugin_dir.parent / f".{name}.bak"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

            # Track in state
            _track_plugin_in_state(name, version, install_source, source_url)

            return InstallResult(
                name=name, version=version,
                status="installed",
                message=f"'{name}' v{version} installed",
                source=source_url or url,
            )

        except Exception as e:
            # Rollback: restore from backup if it existed
            backup_dir = plugin_dir.parent / f".{name}.bak"
            if backup_dir.exists():
                if plugin_dir.exists():
                    shutil.rmtree(plugin_dir)
                shutil.copytree(backup_dir, plugin_dir)
                shutil.rmtree(backup_dir)

            # Clean up temp
            if "tmp_path" in locals():
                Path(tmp_path).unlink(missing_ok=True)

            return InstallResult(
                name=name, version=version or "0.1.0",
                status="failed",
                message=str(e),
                error=str(e),
            )

    def _install_stub(
        self,
        name: str,
        version: str,
        description: str = "",
        author: str = "",
        homepage: str = "",
        repository: str = "",
        install_source: str = "registry",
    ) -> InstallResult:
        """Create a stub plugin (when no download URL is available)."""

        plugin_dir = self.registry.plugins_dir / name
        if plugin_dir.exists():
            return InstallResult(
                name=name, version=version,
                status="skipped",
                message=f"'{name}' already installed",
            )

        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": name,
            "version": version,
            "description": description or f"Plugin '{name}'",
            "author": author or "OpenContext",
            "entry_point": "plugin.py",
            "hooks": [],
            "enabled": True,
            "homepage": homepage,
            "repository": repository,
            "install_source": install_source,
            "source_url": repository,
            "installed_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        (plugin_dir / "plugin.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (plugin_dir / "plugin.py").write_text(
            '"""{} plugin."""\n\nclass OpenContextPlugin:\n    @property\n    def name(self):\n        return "{}"\n    @property\n    def version(self):\n        return "{}"\n    @property\n    def description(self):\n        return "{}"\n'.format(
                description or name,
                name, version,
                description or "",
            ),
            encoding="utf-8",
        )

        _track_plugin_in_state(name, version, install_source, repository)

        return InstallResult(
            name=name, version=version,
            status="installed",
            message=f"'{name}' v{version} installed (scaffold — no download URL available)",
        )

    def find_version(self, name: str, version: str | None = None) -> InstallResult | None:
        """Find and install from all available sources."""

        # Try registry first
        fetcher = RegistryFetcher()
        entry = fetcher.get(name)
        if entry:
            return self.install_from_registry(name, version)

        return None

    @staticmethod
    def _find_exact_version(entry: RegistryPlugin, version: str) -> RegistryVersion | None:
        """Find an exact version in a registry entry.

        Returns None if the version doesn't exist (unlike old _find_version
        which silently fell back to latest).
        """

        for v in entry.versions:
            if v.version == version:
                return v
        return None


# ── Plugin Updater ─────────────────────────────────────────────────────────

class PluginUpdater:
    """Checks for and applies plugin updates."""

    def __init__(self) -> None:
        self.registry = PluginRegistry()
        self.fetcher = RegistryFetcher()

    def check_updates(self) -> list[InstallResult]:
        """Check all installed plugins for updates.

        Returns:
            List of results (skipped = current, installed = updated).
        """

        installed = self.registry.discover()
        results: list[InstallResult] = []

        for plugin in installed:
            if not plugin.enabled:
                continue
            result = self._check_single(plugin)
            results.append(result)

        return results

    def check_updates_for(self, name: str) -> InstallResult:
        """Check a single plugin for updates."""

        info = self.registry.get_info(name)
        if info is None:
            return InstallResult(
                name=name, version="",
                status="failed",
                message=f"Plugin '{name}' not installed",
            )
        return self._check_single(info)

    def _check_single(self, info: PluginInfo) -> InstallResult:
        """Check a single installed plugin for updates."""

        # If installed from registry, check registry for newer version
        if info.install_source in ("registry", "builtin"):
            entry = self.fetcher.get(info.name)
            if entry and entry.versions:
                latest = entry.versions[0]
                if self._is_newer(latest.version, info.version):
                    installer = PluginInstaller(self.registry)
                    if latest.download_url:
                        result = installer._install_from_url(
                            name=info.name,
                            version=latest.version,
                            url=latest.download_url,
                            checksum=latest.checksum,
                            install_source="registry",
                            source_url=entry.repository or "",
                            homepage=entry.homepage,
                            description=entry.description,
                            author=entry.author,
                        )
                        if result.status == "installed":
                            result.status = "updated"
                            result.message = f"'{info.name}' updated {info.version} → {latest.version}"
                        return result
                    else:
                        return InstallResult(
                            name=info.name, version=info.version,
                            status="skipped",
                            message=f"'{info.name}' v{info.version} — update v{latest.version} available but no download URL",
                        )

        # If installed from GitHub, check releases
        if info.install_source == "github" and info.source_url:
            repo = info.source_url.rstrip("/")
            if "github.com" in repo:
                parts = repo.split("github.com/")
                if len(parts) > 1:
                    installer = PluginInstaller(self.registry)
                    result = installer.install_from_github(parts[1], name=info.name)
                    if result.status == "installed":
                        result.status = "updated"
                    return result

        # Check if source URL has a newer version in registry
        if info.source_url:
            for entry in self.fetcher.fetch():
                if (
                    entry.repository == info.source_url
                    or entry.homepage == info.source_url
                ):
                    if entry.versions:
                        latest = entry.versions[0]
                        if self._is_newer(latest.version, info.version):
                            installer = PluginInstaller(self.registry)
                            if latest.download_url:
                                result = installer._install_from_url(
                                    name=info.name,
                                    version=latest.version,
                                    url=latest.download_url,
                                    install_source=info.install_source,
                                    source_url=info.source_url,
                                )
                                if result.status == "installed":
                                    result.status = "updated"
                                return result

        return InstallResult(
            name=info.name, version=info.version,
            status="skipped",
            message=f"'{info.name}' v{info.version} is up to date",
        )

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        """Compare versions. Returns True if latest > current."""

        parts_latest = [int(x) for x in latest.replace("v", "").split(".")]
        parts_current = [int(x) for x in current.replace("v", "").split(".")]

        for a, b in zip(parts_latest, parts_current):
            if a > b:
                return True
            if a < b:
                return False
        return len(parts_latest) > len(parts_current)


# ── Plugin Registry (local) ────────────────────────────────────────────────

class PluginRegistry:
    """Registry for managing locally installed plugins."""

    def __init__(self, plugins_dir: str | Path | None = None) -> None:
        if plugins_dir is None:
            plugins_dir = Path.home() / ".config" / "opencontext" / "plugins"
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        self._plugins: dict[str, Plugin] = {}
        self._commands: dict[str, Callable[..., Any]] = {}
        self._hooks: dict[str, list[Callable[..., Any]]] = {}

    def discover(self) -> list[PluginInfo]:
        """Discover available plugins."""

        plugins = []
        if not self.plugins_dir.exists():
            return plugins

        for path in sorted(self.plugins_dir.iterdir()):
            if path.is_dir() and (path / "plugin.json").exists():
                info = self._read_info(path)
                if info:
                    plugins.append(info)
        return plugins

    def get_info(self, name: str) -> PluginInfo | None:
        """Get plugin info by name."""

        path = self.plugins_dir / name
        if not path.exists() or not (path / "plugin.json").exists():
            return None
        return self._read_info(path)

    def load(self, name: str) -> Plugin | None:
        """Load a plugin by name."""

        if name in self._plugins:
            return self._plugins[name]

        plugin_dir = self.plugins_dir / name
        if not plugin_dir.exists():
            return None

        info_path = plugin_dir / "plugin.json"
        if not info_path.exists():
            return None

        try:
            info = json.loads(info_path.read_text())
            if not info.get("enabled", True):
                return None

            entry_point = info.get("entry_point", "plugin.py")
            module_path = plugin_dir / entry_point

            if not module_path.exists():
                return None

            spec = importlib.util.spec_from_file_location(
                f"opencontext_plugin_{name}", str(module_path)
            )
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            plugin_class = getattr(module, "OpenContextPlugin", None)
            if plugin_class is None:
                return None

            plugin = plugin_class()
            self._plugins[name] = plugin
            return plugin

        except Exception:
            return None

    def enable(self, name: str) -> bool:
        """Enable a plugin."""

        manifest_path = self.plugins_dir / name / "plugin.json"
        if not manifest_path.exists():
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["enabled"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def disable(self, name: str) -> bool:
        """Disable a plugin."""

        manifest_path = self.plugins_dir / name / "plugin.json"
        if not manifest_path.exists():
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["enabled"] = False
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            if name in self._plugins:
                self._plugins[name].shutdown()
                del self._plugins[name]

            return True
        except (json.JSONDecodeError, OSError):
            return False

    def remove(self, name: str) -> bool:
        """Remove a plugin entirely."""

        plugin_dir = self.plugins_dir / name
        if not plugin_dir.exists():
            return False

        try:
            if name in self._plugins:
                self._plugins[name].shutdown()
                del self._plugins[name]

            shutil.rmtree(plugin_dir)

            # Untrack from state
            _untrack_plugin_in_state(name)

            return True
        except OSError:
            return False

    def register_command(self, name: str, handler: Callable[..., Any]) -> None:
        """Register a command handler."""

        self._commands[name] = handler

    def execute_command(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a registered command."""

        handler = self._commands.get(name)
        if handler is None:
            raise KeyError(f"Command not found: {name}")
        return handler(*args, **kwargs)

    def register_hook(self, event: str, handler: Callable[..., Any]) -> None:
        """Register a hook for an event."""

        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)

    def trigger_hook(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Trigger all hooks for an event."""

        results = []
        for handler in self._hooks.get(event, []):
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception:
                pass
        return results

    def list_commands(self) -> list[str]:
        """List registered commands."""

        return list(self._commands.keys())

    def list_hooks(self) -> list[str]:
        """List registered hook events."""

        return list(self._hooks.keys())

    @staticmethod
    def _read_info(path: Path) -> PluginInfo | None:
        """Read PluginInfo from a plugin directory."""

        try:
            info = json.loads((path / "plugin.json").read_text(encoding="utf-8"))
            return PluginInfo(
                name=info["name"],
                version=info.get("version", "0.1.0"),
                description=info.get("description", ""),
                author=info.get("author", ""),
                entry_point=info.get("entry_point", "plugin.py"),
                hooks=info.get("hooks", []),
                enabled=info.get("enabled", True),
                homepage=info.get("homepage", ""),
                repository=info.get("repository", ""),
                install_source=info.get("install_source", "local"),
                source_url=info.get("source_url", ""),
                installed_at=info.get("installed_at", ""),
                updated_at=info.get("updated_at", ""),
            )
        except (json.JSONDecodeError, KeyError, OSError):
            return None


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_top_level_dir(members: list[str]) -> str | None:
    """Get the top-level directory name from a list of archive members."""

    if not members:
        return None
    first = members[0]
    if "/" in first:
        return first.split("/")[0]
    return None


def _track_plugin_in_state(
    name: str, version: str, source: str, source_url: str,
) -> None:
    """Track plugin in StateStore."""

    try:
        from opencontext_core.state import (
            ComponentState,
            StateStore,
        )
        state = StateStore.load()
        now = datetime.now().isoformat()
        existing = state.plugins.get(name)
        if existing:
            existing.version = version
            existing.updated_at = now
            existing.metadata["source"] = source
            existing.metadata["source_url"] = source_url
        else:
            state.plugins[name] = ComponentState(
                id=name,
                name=name,
                version=version,
                enabled=True,
                installed_at=now,
                updated_at=now,
                metadata={"source": source, "source_url": source_url},
            )
        StateStore.save(state)
    except Exception:
        pass


def _untrack_plugin_in_state(name: str) -> None:
    """Remove plugin from StateStore."""

    try:
        from opencontext_core.state import StateStore
        state = StateStore.load()
        state.plugins.pop(name, None)
        StateStore.save(state)
    except Exception:
        pass
