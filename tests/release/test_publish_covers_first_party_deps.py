"""Every first-party dependency of a published package must itself be published.

Guards against the broken-install class where a published wheel (e.g.
opencontext-cli) declares a dependency on a sibling package (e.g.
opencontext-memory) that the publish workflow never uploads to PyPI —
pip resolution then fails for every real user.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PUBLISH_YML = REPO / ".github" / "workflows" / "publish.yml"
PACKAGES_DIR = REPO / "packages"

_DEP_NAME = re.compile(r"^[A-Za-z0-9_.-]+")


def _published_packages() -> set[str]:
    text = PUBLISH_YML.read_text(encoding="utf-8")
    return set(re.findall(r"opencontext-[a-z0-9-]+", text))


def _first_party_deps(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    names = set()
    for dep in deps:
        match = _DEP_NAME.match(dep.strip())
        if match:
            name = match.group(0).lower().replace("_", "-")
            if name.startswith("opencontext"):
                names.add(name)
    return names


def test_publish_matrix_covers_deps_of_published_packages() -> None:
    published = _published_packages()
    assert published, "publish.yml lists no opencontext packages"
    missing: list[str] = []
    for pkg_dir in sorted(PACKAGES_DIR.iterdir()):
        pyproject = pkg_dir / "pyproject.toml"
        if not pyproject.exists():
            continue
        pkg_name = pkg_dir.name.replace("_", "-")
        if pkg_name not in published:
            continue
        for dep in _first_party_deps(pyproject):
            if dep not in published:
                missing.append(f"{pkg_name} depends on {dep}, absent from publish.yml")
    assert not missing, "published packages depend on unpublished siblings:\n" + "\n".join(missing)
