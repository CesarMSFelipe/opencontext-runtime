"""Self-update system — checks PyPI for newer versions.

Uses the PyPI JSON API to check for updates without
external services or telemetry.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from opencontext_core.state import StateStore


# ── Data ───────────────────────────────────────────────────────────────────

@dataclass
class UpdateCheck:
    """Result of an update check."""

    current_version: str
    latest_version: str
    is_outdated: bool
    checked_at: str = ""
    release_url: str = ""
    release_notes: str = ""


@dataclass
class UpdateState:
    """Cached update check state."""

    check: UpdateCheck | None = None
    last_check: str = ""
    skip_version: str = ""


PACKAGE_NAME = "opencontext-core"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
CACHE_DURATION = timedelta(hours=24)


# ── Update Check ───────────────────────────────────────────────────────────

class UpdateChecker:
    """Check for newer versions on PyPI."""

    CACHE_FILE = Path.home() / ".config" / "opencontext" / "update-cache.json"

    @classmethod
    def get_current_version(cls) -> str:
        """Get the currently installed version."""

        try:
            import importlib.metadata
            return importlib.metadata.version(PACKAGE_NAME)
        except importlib.metadata.PackageNotFoundError:
            return "0.0.0"

    @classmethod
    def check(cls, force: bool = False) -> UpdateCheck:
        """Check PyPI for the latest version.

        Args:
            force: Skip cache and fetch from PyPI.

        Returns:
            UpdateCheck with version comparison.
        """

        current = cls.get_current_version()

        # Check cache first
        if not force:
            cached = cls._load_cache()
            if cached and cached.last_check:
                last = datetime.fromisoformat(cached.last_check)
                if datetime.now() - last < CACHE_DURATION and cached.check:
                    return cached.check

        # Fetch from PyPI
        try:
            req = Request(PYPI_JSON_URL, headers={"User-Agent": "OpenContext/1.0"})
            with urlopen(req, timeout=10) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode())

            latest = data["info"]["version"]
            release_url = data["info"].get("release_url", "")
            # Build a release notes URL from the project URLs
            project_urls = data["info"].get("project_urls", {}) or {}
            release_notes = (
                project_urls.get("Release notes", "")
                or project_urls.get("Changelog", "")
                or project_urls.get("Homepage", "")
            )

            result = UpdateCheck(
                current_version=current,
                latest_version=latest,
                is_outdated=cls._compare_versions(current, latest) < 0,
                checked_at=datetime.now().isoformat(),
                release_url=release_url,
                release_notes=release_notes,
            )
        except Exception:
            # If we can't reach PyPI, return current version as latest
            result = UpdateCheck(
                current_version=current,
                latest_version=current,
                is_outdated=False,
                checked_at=datetime.now().isoformat(),
            )

        # Cache result
        state = UpdateState(check=result, last_check=result.checked_at)
        cls._save_cache(state)

        # Update StateStore
        try:
            store_state = StateStore.load()
            store_state.last_update_check = result.checked_at
            StateStore.save(store_state)
        except Exception:
            pass

        return result

    @classmethod
    def upgrade(cls) -> dict[str, Any]:
        """Run pip install --upgrade for the package.

        Returns:
            Dict with status, message, and output.
        """

        check = cls.check()
        if not check.is_outdated:
            return {"status": "current", "message": f"Already at latest version {check.current_version}"}

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    f"{PACKAGE_NAME}",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                # Mark synced after upgrade
                StateStore.mark_synced()
                return {
                    "status": "upgraded",
                    "from": check.current_version,
                    "to": check.latest_version,
                    "message": f"Upgraded from {check.current_version} to {check.latest_version}",
                    "output": result.stdout,
                }
            else:
                return {
                    "status": "failed",
                    "message": "pip upgrade failed",
                    "error": result.stderr,
                }
        except subprocess.TimeoutExpired:
            return {"status": "failed", "message": "pip upgrade timed out"}
        except FileNotFoundError:
            return {"status": "failed", "message": "pip not found"}

    @classmethod
    def skip_version(cls, version: str) -> None:
        """Skip a specific version in future checks."""

        state = cls._load_cache()
        state.skip_version = version
        cls._save_cache(state)

    @classmethod
    def _compare_versions(cls, v1: str, v2: str) -> int:
        """Compare two semver strings. Returns -1, 0, or 1."""

        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        for a, b in zip(parts1, parts2):
            if a < b:
                return -1
            if a > b:
                return 1
        return 0

    @classmethod
    def _load_cache(cls) -> UpdateState:
        """Load cached update state."""

        if cls.CACHE_FILE.exists():
            try:
                data = json.loads(cls.CACHE_FILE.read_text(encoding="utf-8"))
                check_data = data.get("check")
                check = UpdateCheck(**check_data) if check_data else None
                return UpdateState(
                    check=check,
                    last_check=data.get("last_check", ""),
                    skip_version=data.get("skip_version", ""),
                )
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        return UpdateState()

    @classmethod
    def _save_cache(cls, state: UpdateState) -> None:
        """Save cached update state."""

        cls.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "check": {
                "current_version": state.check.current_version,
                "latest_version": state.check.latest_version,
                "is_outdated": state.check.is_outdated,
                "checked_at": state.check.checked_at,
                "release_url": state.check.release_url,
                "release_notes": state.check.release_notes,
            }
            if state.check
            else None,
            "last_check": state.last_check,
            "skip_version": state.skip_version,
        }
        cls.CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
