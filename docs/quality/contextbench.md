# ContextBench

ContextBench is the public, deterministic benchmark for OpenContext context
selection. It checks what OpenContext can prove without making provider calls:

- expected source coverage,
- forbidden source exclusion,
- token reduction against the indexed project baseline,
- trace-backed context preparation.

It is not a model-answer benchmark. Use provider-specific answer evals after
ContextBench if you need to prove final response quality.

## Run the included suite

```bash
opencontext eval contextbench examples/evals/contextbench.yaml \
  --root . \
  --max-tokens 6000 \
  --min-token-reduction 0.50
```

The command exits with a non-zero status when a gate fails.

## CI Integration

ContextBench checks can run automatically in CI via the generated GitHub Actions workflow:

```bash
# Initialize checks + generate ContextBench workflow
opencontext ci-check init

# Or generate the workflow independently
opencontext ci-check github-actions
```

This creates `.github/workflows/opencontext-contextbench.yml` that runs
`opencontext ci-check run --json` on every push and pull request, uploads the
report as an artifact, and fails the build if any checks fail.

See [CI Checks](../guides/ci-checks.md) for defining custom check rules.

## Case format

```yaml
cases:
  - id: runtime-first-context
    query: "How does the runtime prepare compact context for a non-CLI agent adapter?"
    expected_sources:
      - "packages/opencontext_core/opencontext_core/runtime.py"
    forbidden_sources:
      - ".storage/"
      - ".opencontext/"
    min_source_coverage: 1.0
```

Use path fragments instead of absolute paths so the suite works across machines.
Keep cases narrow. A useful benchmark case names a concrete behavior, subsystem,
or risk.

## Interpreting results

- `source_coverage`: fraction of expected source fragments found in the pack.
- `token_reduction`: estimated reduction versus the indexed repository baseline.
- `context_tokens`: tokens in the prepared context pack.
- `baseline_tokens`: estimated full project token baseline.
- `missing_sources`: expected source fragments not retrieved.
- `forbidden_hits`: forbidden source fragments retrieved.

For release claims, publish the suite file, command, OpenContext version, and
JSON output.

