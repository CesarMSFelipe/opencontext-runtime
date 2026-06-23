# Architecture Boundaries

## Purpose
Do not import FastAPI, CLI frameworks, provider SDKs, LangChain, LlamaIndex, vector databases, or framework-specific logic into core.

## Current Status
Development workflows are local and test-driven. Core defines provider-neutral adapter contracts in `opencontext_core/providers/`; SDK-backed integrations, if added, belong in an application-level package outside core (there is none currently).

## Boundary Rules
- Core may define provider-neutral policy models and protocols.
- Core must not import provider SDKs.
- CLI/API may depend on core, but core must not import CLI/API frameworks.
- Technology-specific profile logic belongs in `packages/opencontext_profiles`.

## Related Commands
```bash
pytest
ruff check .
ruff format --check .
mypy packages/opencontext_core
```

## Implemented Code
- `packages/opencontext_core/`
- `packages/opencontext_cli/`
- `packages/opencontext_profiles/`
- `tests/core/`
