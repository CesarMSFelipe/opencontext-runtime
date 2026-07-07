# Acceptance harness (black-box)

External acceptance suite for `docs/product-contract/ACCEPTANCE_CONTRACT.md`
(AC-001..AC-030). It drives the real `opencontext` binary as a subprocess and
never imports `opencontext_*` modules: filesystem, JSON, exit codes and run
artifacts are the only observed surfaces.

## How to run

Against the active venv (default binary = `shutil.which("opencontext")`):

```bash
source .venv/bin/activate
python -m pytest tests/acceptance -q
```

Against any other binary (installed package, fresh venv, pyz):

```bash
python -m venv /tmp/oc-acceptance-venv
/tmp/oc-acceptance-venv/bin/pip install opencontext-cli==X.Y.Z
python -m pytest tests/acceptance -q --oc-bin /tmp/oc-acceptance-venv/bin/opencontext
```

Smoke subset only (SMOKE-001..010 equivalents, PR lane):

```bash
python -m pytest tests/acceptance -q -m smoke
```

Release scenarios (AC-029/AC-030) resolve an artifact from `--oc-wheel`, then
`dist/*.whl`, then `dist/opencontext.pyz`, and skip with a clear reason when
none exists.

## Isolation guarantees

Every test runs with:

- an isolated tmp workspace (optionally seeded from `fixtures/`);
- an isolated `$HOME` + `XDG_*` dirs (no global `~/.opencontext` pollution in
  either direction);
- all `OPENCONTEXT_*`, `PYTHONPATH`, `VIRTUAL_ENV` variables stripped from the
  subprocess environment.

## Known-gap policy

Where the product does not yet satisfy the target contract, the REAL assertion
is still written and marked `@pytest.mark.xfail(reason="GAP-xxx: ...",
strict=False)`. Assertions are never watered down to pass; when a gap closes,
its xfail turns into an unexpected pass (XPASS) and the marker gets removed.

## Layout

- `conftest.py` — `--oc-bin`/`--oc-wheel` options, `oc_bin` fixture, isolated
  workspace factory, shared session runs (one paid workflow run reused by
  several ACs).
- `helpers/` — subprocess helpers (`cli.py`), JSON purity + envelope
  assertions (`json_assertions.py`), workspace/env factory (`workspace.py`),
  composed CLI operations (`ops.py`).
- `fixtures/` — small committed projects (never collected in place):
  `py_bugfix_basic`, `py_bugfix_no_tests`, `py_large_context`,
  `sdd_feature_basic`, `memory_reuse_basic`.
- `test_acceptance_*.py` — scenarios grouped by contract area; each test's
  docstring starts with the AC id it protects.
