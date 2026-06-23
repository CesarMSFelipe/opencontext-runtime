# Release Checklist

Use this checklist before publishing a release or announcing OpenContext Runtime publicly.

## Functional Readiness

- Run `OpenContextRuntime().setup_project(...)` against a clean temporary project.
- Run `prepare_context(...)` for at least one architecture, API, integration, security, and token
  efficiency query.
- Confirm expected sources appear in `included_sources`.
- Confirm `omitted_sources` and context-pack omission records are present when candidates exceed
  budget.
- Confirm `trace_id` round-trips through `load_trace(trace_id)`.
- Confirm generated context does not contain raw secrets.
- Confirm `.opencontext/`, `.storage/`, `.agents/`, virtualenvs, caches, and traces are ignored.

## Validation Commands

```bash
pytest
ruff check .
ruff format --check .
mypy packages/opencontext_core
python -m build packages/opencontext_core
python -m build packages/opencontext_profiles
python -m build packages/opencontext_cli
python -m build packages/opencontext_api
```

## Documentation Checks

- README explains runtime-first setup without CLI commands.
- README explains CLI as optional.
- README distinguishes agent tools from LLM providers.
- README states that OpenContext indexes the non-ignored repo but sends only packed context to the
  model.
- README clearly marks scaffolded features and does not imply enterprise certification.
- Security policy explains private vulnerability reporting and safe defaults.

## Packaging Checks

- Package versions are aligned.
- Package metadata is present for each package.
- CI installs validation tools explicitly.
- Security workflow audits installed package dependencies.
- No local runtime state is present in `git status --short`.

## Release Decision

Do not publish if any of these are true:

- Core runtime cannot setup, index, prepare context, and load traces from a clean project.
- Secret redaction fails on context or trace persistence.
- README claims a feature is implemented when it is only scaffolded.
- CI relies on undeclared tools.
- Build artifacts include local traces, caches, virtualenvs, generated analysis reports, or secrets.
