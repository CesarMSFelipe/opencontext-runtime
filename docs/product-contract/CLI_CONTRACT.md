# CLI_CONTRACT

The CLI is a stable API for humans and agents. Every stable command follows this contract.

Verified by: AC-001, AC-002, AC-004, AC-009, AC-011, AC-024.

## Global flags

Stable commands support the subset of these flags that applies to them; where supported, the
flag name and semantics must be uniform:

| Flag | Meaning |
|---|---|
| `--json` | Machine-readable output; activates the JSON purity rule below |
| `--quiet` | Suppress human-facing progress/status text |
| `--verbose` | Extra diagnostic detail (stderr in `--json` mode) |
| `--dry-run` | Report what would happen without changing anything |
| `--root <path>` | Project root (default: cwd) |
| `--config <path>` | Explicit config file (overrides `<root>/opencontext.yaml`) |
| `--no-color` | Disable ANSI styling |

> Current: the shared flag layer lives in `opencontext_cli/contracts/flags.py`.
> `--quiet` and `--no-color` are implemented uniformly on every stable command (top-level
> `opencontext --quiet <command>` and trailing `opencontext <command> --quiet`, plus the
> `OPENCONTEXT_QUIET` / `NO_COLOR` env aliases). `--json` parses on every stable leaf
> command where it applies (`version`, `status`, `doctor`, `index`, `install`, `run`,
> `uninstall`, `pack`, `init`, `clean`); tree-style commands (`config`, `memory`,
> `knowledge-graph`, `runs`, `sdd`, `harness`) expose `--json` on their subcommands.
> `pack --json` is the documented spelling; `--format json` remains as a back-compat
> alias (additive migration). The exact per-command flag subset is frozen in
> `STABLE_COMMAND_FLAGS` and pinned by `tests/cli/test_cli_flags_matrix.py`.
> Remaining documented deviations: `--root` is a positional argument on `index`,
> `status`, `clean`, `install`, and `pack` (option form only on `run`/`uninstall`);
> `--verbose` exists per-subcommand (`sdd`, `memory`) and as `version --output verbose`;
> `--profile` applies to `init`/`run`; `--verify` applies to `uninstall`/scopes.

## JSON purity rule

With `--json`:

- stdout contains ONLY the JSON document — parseable with `json.loads(stdout)`;
- all human-facing text (progress, hints, warnings banners) goes to stderr or is suppressed;
- `--json` implies non-interactive behavior (no prompts).

## Standard error envelope

Every stable command failure in `--json` mode emits:

```json
{
  "ok": false,
  "status": "failed",
  "error": {
    "code": "TDD_RED_NOT_PROVEN",
    "message": "TDD strict requires a failing test before mutation.",
    "hint": "Add or modify a relevant test, run it, and ensure it fails before applying the fix.",
    "details": {"workflow": "oc-flow", "phase": "apply"}
  }
}
```

Rules: `error.code` is a stable SCREAMING_SNAKE identifier (semver-protected); `message` is
human-readable; `hint` is an actionable next step (P0 errors must have one); `details` is an
open object. `status` uses only canonical states (`RUN_STATE_CONTRACT.md`).

The stable code set is frozen in `opencontext_cli/contracts/error_codes.py` and pinned by
`tests/cli/test_error_code_catalog.py`; cataloged P0 codes reject construction without a
hint. The top-level dispatcher guarantees the envelope for every stable-command failure in
JSON mode: otherwise-unhandled `OpenContextError` / `FileNotFoundError` / `PermissionError` /
unexpected exceptions render `OPERATION_FAILED` / `FILE_NOT_FOUND` / `PERMISSION_DENIED` /
`UNEXPECTED_ERROR` (pinned by `tests/cli/test_cli_json_envelope_matrix.py`). Historical
lowercase codes (`run_not_found`, `target_not_found`, `pack_unreadable`) were migrated to
their SCREAMING_SNAKE forms to conform to this rule.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success (`passed`) or `not_applicable` |
| 1 | Generic failure |
| 2 | CLI usage error (bad arguments, unknown flags) |
| 3 | Invalid configuration / `needs_configuration` |
| 4 | Policy or security blocked / approval denied |
| 5 | Executor or model required (`needs_executor`) |
| 6 | TDD strict violated |
| 7 | SDD artifacts missing or inconsistent |
| 8 | Verification / test failure |
| 9 | Install / uninstall incomplete |

Rules:

- Exit code must always match the final state (`RUN_STATE_CONTRACT.md` mapping table).
- `passed` may exit 0 only when mandatory evidence exists.
- `failed`, `blocked`, `needs_context`, TDD violations, and verification failures never exit 0.

> Current → Target: the current CLI mostly uses 0/1/2 (argparse supplies 2). Codes 3–9 are the
> freeze target, to be centralized in an `exit_codes` module consumed by every stable command.

## Semver compatibility promise (stable commands)

Within a major version, for `stable` commands:

- command names, documented flags, JSON field names, error codes, and exit codes are not
  removed or repurposed;
- new JSON fields and new flags may be added (consumers must ignore unknown fields);
- canonical states and their exit-code mapping do not change;
- breaking any of the above requires a major version bump and a CHANGELOG entry.

`preview` commands carry no such promise; `internal` commands carry none at all.
