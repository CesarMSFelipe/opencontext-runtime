# Installation

## Purpose
Install OpenContext Runtime for local development, testing, or production use.

## Current Status
All packages can be installed from source. PyPI publishing is configured but packages are not yet published.

## From Source (Development)
```bash
git clone https://github.com/CesarMSFelipe/OpenContext-Runtime.git
cd OpenContext-Runtime
pip install -e packages/opencontext_core -e packages/opencontext_cli
# Optional: install API and profiles
pip install -e packages/opencontext_api -e packages/opencontext_profiles
opencontext --help
```

## From PyPI (When Published)
```bash
pip install opencontext-core opencontext-cli
# Optional: install API and profiles
pip install opencontext-api opencontext-profiles
```

## Post-Installation

After installing, run the setup wizard to configure your project:

```bash
cd your-project
opencontext install
```

`opencontext install` works on **Linux, macOS, and Windows** (via PowerShell). It auto-detects
your project stack and configures SDD/TDD, project index, knowledge graph, and agent integrations
in one step. Use `opencontext install --yes` for non-interactive setup.

## Implemented Code
- CLI entry point: `packages/opencontext_cli/opencontext_cli/main.py`
- Core runtime: `packages/opencontext_core/opencontext_core/`
- API server: `packages/opencontext_api/opencontext_api/`
- Technology profiles: `packages/opencontext_profiles/opencontext_profiles/`
- Installer: `install.sh` (Linux/macOS), `install.ps1` (Windows)

## Publishing
Packages are built and ready for PyPI publishing. The GitHub Actions workflow will publish on releases.
