# CI Checks

OpenContext provides a lightweight CI check system for automated code reviews. Checks are defined as markdown files with YAML frontmatter and can be run locally or in CI pipelines.

## Quick Start

```bash
# Initialize checks directory with sample checks
opencontext ci-check init

# List discovered checks
opencontext ci-check list

# Run all checks
opencontext ci-check run

# Run on a specific file
opencontext ci-check run --file src/auth.py

# Create a new check
opencontext ci-check create "My Custom Check"
```

## Check Format

Checks live in `.opencontext/checks/` as markdown files:

```markdown
---
name: Security Review
description: Review code for common security issues
severity: error
files:
- "*.py"
- "*.js"
- "*.ts"
patterns:
- "password\\s*="
- "secret\\s*="
- "token\\s*="
- "api_key\\s*="
- "eval\\s*\\("
- "exec\\s*\\("
auto_fix: false
---
Review this code for security issues:
- No hardcoded secrets or credentials
- No dangerous eval/exec usage
- Proper input validation
- Safe error handling without information leakage
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Check name |
| `description` | Yes | What this check does |
| `severity` | Yes | `info`, `warning`, `error`, `critical` |
| `files` | No | Glob patterns for target files |
| `patterns` | No | Regex patterns to search for |
| `auto_fix` | No | Whether auto-fix is supported |

## Severity Levels

- **info**: FYI, does not fail the check run
- **warning**: Should fix, but does not block
- **error**: Must fix, blocks merge
- **critical**: Security issue, blocks merge immediately

## CI Integration

Generate a GitHub Actions workflow automatically:

```bash
opencontext ci-check github-actions
```

Or include it during initialization:

```bash
opencontext ci-check init
```

This creates `.github/workflows/opencontext-contextbench.yml` that runs checks
on every push and pull request, uploads the JSON report as an artifact, and
fails the build on check failures.

Manual pipeline example:

```yaml
# .github/workflows/checks.yml
name: OpenContext Checks
on: [pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install opencontext-cli
      - run: opencontext ci-check init --no-workflow
      - run: opencontext ci-check run --json > report.json
      - uses: actions/upload-artifact@v4
        with:
          name: check-report
          path: report.json
```

## Programmatic Usage

```python
from opencontext_core.quality.ci_checks import CheckRunner

runner = CheckRunner()
runner.init_checks_directory()

results = runner.run_all_checks()
report = runner.generate_report(results)

if not report["summary"]["success"]:
    print("Checks failed!")
```
