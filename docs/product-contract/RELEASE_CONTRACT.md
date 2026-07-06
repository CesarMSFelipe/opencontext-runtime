# RELEASE_CONTRACT

A release ships only if the built, installed package passes acceptance as a real user would
run it. No green pipeline, no publish.

Verified by: AC-029, AC-030, INST-001..INST-009, SMOKE-001..SMOKE-010.

## Release gate pipeline

```
clean checkout
→ build package                  (wheel/sdist/pyz from a pristine tree)
→ inspect artifact hygiene       (forbidden-content scan, AC-029)
→ install in fresh venv          (pip install dist/*.whl into a new venv)
→ run smoke acceptance           (SMOKE-001..010, < 60 s)
→ run full acceptance            (AC-001..AC-030 with --oc-bin <venv>/bin/opencontext, < 5 min)
→ uninstall verify               (uninstall --purge --verify leaves no managed residue)
→ generate release report
→ publish                        (token-authenticated; see CI notes below)
```

Any failing stage stops the pipeline; there is no manual override for stable commands.

### CI wiring

The gate is enforced in Actions: `publish.yml` calls `release-acceptance.yml` as a reusable
workflow (`workflow_call`) inside the same workflow run, and the `build-and-publish` job
declares `needs: release-acceptance`. No wheel is uploaded unless the DoD sequence, artifact
hygiene audit (AC-029), fresh-venv install + acceptance against the installed wheels
(AC-030), and uninstall-verify all pass on the exact ref being published — including
tag-push publishes, which previously ran ungated. `release-acceptance.yml` stays usable
standalone via `workflow_dispatch` and on release publication. Guarded by
`tests/release/test_publish_gated_on_acceptance.py`.

## Artifact hygiene — forbidden in the published artifact

```
.git/
.venv/  venv/  .ci-venv/
.pytest_cache/  .mypy_cache/  .ruff_cache/
__pycache__/
.opencontext/
.coverage
stray local *.egg-info
local logs
local state (runs, memory stores, indexes)
```

The hygiene inspector unpacks the built artifact and fails the gate on any match (AC-029).

## Release report contents

Persisted with the release (e.g. `artifacts/release-report-<version>.json` + attached to the
GitHub release):

| Field | Content |
|---|---|
| `version` | Exact published version; must match `opencontext version --json` post-install |
| `checksums` | sha256 per published file (wheel, sdist, pyz) |
| `acceptance_summary` | Suite results: total/passed/failed per suite (smoke, full), duration, `--oc-bin` used |
| `uninstall_verify` | Result of the post-acceptance uninstall verification |
| `known_limitations` | Explicit list of preview/incomplete areas shipped in this version |

## Rules

1. Acceptance runs against the INSTALLED package, never the source tree (AC-030).
2. `version --json` after fresh install equals the tag being published (regression: it must
   never report a placeholder like `0.0.0`).
3. No stable command may be broken or a placeholder at release time (see
   `PRODUCT_CONTRACT.md` DoD #16).
4. The uninstall step proves the manifest round-trip: install → use → uninstall → no managed
   residue (`INSTALL_UNINSTALL_CONTRACT.md`).
5. Publishing uses token authentication (`secrets.PYPI_API_TOKEN`) in `publish.yml`; a failed
   publish is re-triggered by re-tagging after the gate passes again.

> Status: the single gated pipeline above — hygiene inspector, external acceptance against
> the installed package, uninstall-verify stage, and the machine-readable release report —
> is implemented in `release-acceptance.yml`, and `publish.yml` cannot upload without it
> passing in the same run (see CI wiring above).
