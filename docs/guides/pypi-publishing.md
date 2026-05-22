# PyPI Publication Guide

## Package Architecture

OpenContext Runtime is split into **5 packages** on PyPI:

| Package | PyPI Name | Dependencies | Description |
|---------|-----------|--------------|-------------|
| `opencontext-core` | `opencontext-core` | (none) | Core runtime — config, indexing, KG, learning, plugin system |
| `opencontext-cli` | `opencontext-cli` | `opencontext-core`, `opencontext-profiles` | CLI entry point (`opencontext` command) |
| `opencontext-api` | `opencontext-api` | `opencontext-core`, `opencontext-profiles`, `fastapi` | FastAPI adapter for HTTP access |
| `opencontext-profiles` | `opencontext-profiles` | `opencontext-core` | Technology profiles (Python, Node, Drupal, etc.) |
| `opencontext-providers` | `opencontext-providers` | `opencontext-core` | Provider adapters (OpenAI, Anthropic, etc.) |

## Release Order

Packages must be published in dependency order:

```
1. opencontext-core     (no deps → publish first)
2. opencontext-profiles (depends on core)
3. opencontext-providers (depends on core)
4. opencontext-cli      (depends on core + profiles)
5. opencontext-api      (depends on core + profiles)
```

## Release Checklist

### Prerequisites

- [ ] PyPI account created
- [ ] API token configured: `~/.pypirc`
- [ ] `build` and `twine` installed: `pip install build twine`
- [ ] Version bumped in all `pyproject.toml` files
- [ ] All tests pass: `python -m pytest tests`

### Step-by-Step

For each package in release order:

```bash
# 1. Clean previous builds
rm -rf dist/ build/ *.egg-info

# 2. Build
python -m build

# 3. Check the package (fix warnings)
twine check dist/*

# 4. Install locally and test
pip install dist/opencontext_core-0.2.0-py3-none-any.whl

# 5. Upload to PyPI
twine upload dist/*
```

### Full Release Script

```bash
#!/usr/bin/env bash
set -euo pipefail

PACKAGES=(
  "packages/opencontext_core"
  "packages/opencontext_profiles"
  "packages/opencontext_providers"
  "packages/opencontext_cli"
  "packages/opencontext_api"
)

for pkg in "${PACKAGES[@]}"; do
  echo "=== Publishing $pkg ==="
  cd "$pkg"
  rm -rf dist/ build/ *.egg-info
  python -m build
  twine check dist/*
  twine upload dist/*
  cd -
  echo ""
done

echo "All packages published!"
```

## Version Strategy

| Version | Status | Notes |
|---------|--------|-------|
| 0.1.0 | Previous | MVP — core indexing, repo maps, memory |
| 0.2.0 | Current dev | SDD orchestration, agent system, learning, quality gates |
| 1.0.0 | Planned | Stable API, production ready |

## Dependencies Per Package

### opencontext-core
```
pydantic>=2.6
PyYAML>=6.0
tree-sitter>=0.24
tree-sitter-python>=0.25
watchdog>=6.0
rich>=13.0
prompt-toolkit>=3.0
```

### opencontext-cli
```
opencontext-core>=0.2.0
opencontext-profiles>=0.2.0
```

### opencontext-api
```
opencontext-core>=0.2.0
opencontext-profiles>=0.2.0
fastapi>=0.110
httpx>=0.27
```

### opencontext-profiles
```
opencontext-core>=0.1.0
```

### opencontext-providers
```
opencontext-core>=0.1.0
```

## Files Distributed Per Package

### opencontext-core
```
opencontext_core/
├── __init__.py           # Public API exports
├── config.py             # Load/save config, models
├── runtime.py            # Main runtime
├── user_prefs.py         # User preferences persistence
├── wizard.py             # Interactive configuration wizard
├── plugin_system.py      # Plugin registry and base classes
├── plugins/manifest.py   # Plugin security manifest
├── ... (indexing, safety, trace, memory, etc.)
```

### opencontext-cli
```
opencontext_cli/
├── __init__.py
├── main.py               # CLI entry point (opencontext command)
├── commands/
│   ├── config_cmd.py     # config wizard/show/set/get/reset
│   ├── plugin_cmd.py     # plugin install/list/remove/enable/disable
│   ├── kg_cmd.py         # knowledge-graph commands
│   ├── git_cmd.py        # git commands
│   └── ...
```

## Known Issues & Pre-Release Checklist

### Implicit Namespace Packages

Several subdirectories in `opencontext-core` lack `__init__.py`:

| Directory | Status | .py Files |
|-----------|--------|-----------|
| `adapters/` | ⚠️ No __init__.py | 2 files |
| `compression/` | ⚠️ No __init__.py | 1 file |
| `doctor/` | ⚠️ No __init__.py | 2 files |
| `dx/` | ⚠️ No __init__.py | 7 files |
| `plugins/` | ⚠️ No __init__.py | 1 file |
| `providers/` | ⚠️ No __init__.py | 1 file |
| `quality/` | ⚠️ No __init__.py | 1 file |
| `skills/` | ⚠️ No __init__.py | 3 files |
| `workflow_packs/` | ⚠️ No __init__.py | 2 files |
| `workspace/` | ⚠️ No __init__.py | 1 file |

These work as **implicit namespace packages** (PEP 420) in Python 3.12+ and
are included correctly in the built wheel. All imports work both in editable
mode and from the wheel install.

**Action before 1.0.0**: Add `__init__.py` to each directory to avoid
potential issues with older packaging tools or alternative build backends.

### Pre-Release Checklist

- [ ] All packages build successfully: `python -m build`
- [ ] `twine check` passes: no warnings
- [ ] Install from .whl: all imports work
- [ ] Install from .whl: `opencontext --version` works
- [ ] Install from .whl: `opencontext config wizard --non-interactive` configures correctly
- [ ] Install from .whl: `opencontext config show` displays preferences
- [ ] Install from .whl: `opencontext plugin list` lists plugins
- [ ] Install from .whl: `opencontext` commands work outside any project directory
- [ ] Version numbers consistent across all 5 `pyproject.toml` files
- [ ] All tests pass: `python -m pytest tests`

## Verification After Installation

After publishing, verify all packages install correctly:

```bash
pip install opencontext-cli
opencontext --version
opencontext config wizard --non-interactive
opencontext config show
opencontext plugin list
```

Expected output — all commands work without needing a project directory.
