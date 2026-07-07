# INSTALL_UNINSTALL_CONTRACT

Installation and uninstallation are separated into three scopes. Every install writes a
manifest; uninstall is manifest-driven and never guesses.

Verified by: AC-003, AC-022, AC-023, INST-001..INST-009, SMOKE-003, SMOKE-010.

## Scopes and command mapping

| Scope | What it owns | Real commands today |
|---|---|---|
| `product` | The OpenContext binary + HOME state (`~/.config/opencontext`, `~/.opencontext`, the whole XDG state root `~/.local/state/opencontext` — per-project hash dirs included — and the XDG cache dir) | `pipx install opencontext-cli` / `pip install` / `install.sh` / `install.ps1`; removal via `pipx uninstall` + `uninstall --full --global-state` |
| `workspace` | Per-repo state: `opencontext.yaml`, the in-repo `.opencontext/` config subdirs, plus THIS project's XDG state dir (`~/.local/state/opencontext/projects/<hash>/` — indexes, runs, memory in user mode) | `init` (wizard), `install` (quick setup); removal via `clean` or `uninstall --scope workspace --purge` |
| `agents` | Agent client config: MCP entries, instruction blocks, generated agent files | `setup [AGENT...]`; removal via `uninstall [AGENT...]` |

> The `product|workspace|agents` top-level commands exist as preview aliases: each exposes
> `install`/`status`/`uninstall` subcommands (`workspace` also accepts `init`) that delegate to
> the flat commands above — `product uninstall` → `uninstall --scope global`, `workspace
> init/status/uninstall` → `install <root>` / `status <root>` / `uninstall --scope workspace`,
> `agents install/status/uninstall` → `setup` / `capabilities` / `uninstall [AGENT...]`.
> `uninstall --scope {workspace,global,all}` selects state scope (`local` is a legacy alias for
> `workspace`); `--purge` deletes project artifacts; `--full` sweeps ledger-tracked files;
> `--verify` scans for residue and reports pass/fail. These flags stay stable as the scope
> selectors.

## Product manifest schema

```json
{
  "schema_version": 2,
  "install_id": "uuid4, stable across reinstalls",
  "install_method": "pipx|pip|venv|editable|installer|manual",
  "product_version": "1.7.0",
  "created_paths": [],
  "modified_files": [],
  "shell_profile_blocks": [{"path": "~/.bashrc", "marker": "# OpenContext Runtime"}],
  "symlinks": [{"path": "~/.local/bin/opencontext", "target": "~/.opencontext/venv/bin/opencontext"}],
  "env_vars": [],
  "agent_configs": [],
  "state_paths": [],
  "timestamp": "2026-07-06T00:00:00Z"
}
```

## Workspace manifest schema

```json
{
  "schema_version": 2,
  "install_id": "uuid4, stable across reinstalls",
  "product_version": "1.7.0",
  "install_method": "init|install",
  "created_paths": [".opencontext", "opencontext.yaml"],
  "modified_files": [],
  "shell_profile_blocks": [],
  "symlinks": [],
  "state_paths": [".opencontext", "/home/user/.local/state/opencontext/projects/<hash>"],
  "agent_configs": [],
  "timestamp": "2026-07-06T00:00:00Z"
}
```

> Implemented (INST-001/INST-002/INST-MANIFEST-FIELDS): both scopes write these
> fields on top of the v1 ownership fields (`app, project_root, project_id, created_by,
> version, created_at`) in `oc-manifest.json` — the workspace scope at `<root>/.opencontext/`
> via `install`, the product scope at `~/.opencontext/` via `product install`, the full
> `install` global step, and install.sh/install.ps1. The workspace scope never writes
> shell profile blocks, symlinks, or env vars, so those stay `[]` there.

> `state_paths` follows the storage mode (PRODUCT_CONTRACT §Storage modes): in `user` mode
> (default) the install records the ABSOLUTE XDG project state dir
> (`~/.local/state/opencontext/projects/<hash>/`) — where execution state (sessions, runs,
> checkpoints, receipts, decision logs, learning) actually lives — alongside any in-repo
> config dirs it created. Legacy in-repo state entries (`.opencontext/runs`, ...) appear
> only for `local`-mode or pre-migration installs. Safety gate: an absolute `state_paths`
> entry is only purged when it is OpenContext-named or carries the OpenContext ownership
> manifest (`is_owned`). The workspace purge removes only THIS project's hash dir; the
> global purge removes the whole XDG state root, project hash dirs included. A
> workspace-scope `--verify` never reports HOME-level/XDG global state as residue — that
> state belongs to the `global` scope scan.

## Uninstall algorithm

`uninstall <scope> --purge --verify` must, in order:

1. Read the scope's manifest (missing manifest → `blocked` with hint, exit 3).
2. With `--dry-run`: list exactly what would be deleted, delete nothing, exit 0.
3. Delete managed paths only (paths recorded in `created_paths`/`state_paths`/ledger).
4. Revert shell profile blocks it created; remove managed symlinks and env vars.
5. Remove managed agent config blocks/MCP entries (backup first; leave user content intact).
6. Verify: rescan for managed residue.
7. Report: removed paths, reverted blocks, and any UNMANAGED leftovers found (reported,
   never deleted).
8. Exit: 0 when no managed residue remains; 9 when managed residue could not be removed.
   Implemented: `--verify` exits 9 (`INSTALL_INCOMPLETE`) on managed residue and the `--json`
   report carries an additive `exit_code` field mirroring the process exit code.

## Safety rules

- NEVER delete a path that is not registered in a manifest/ledger without explicit,
  per-path confirmation.
- Unmanaged residue is reported, not silently removed.
- `--verify` alone is read-only: scan and report, remove nothing.
- Reinstall over an existing install is idempotent and must not duplicate manifest entries
  (INST-003).
- Every destructive step is preceded by a backup when it touches user-owned files (agent
  configs, shell profiles).
