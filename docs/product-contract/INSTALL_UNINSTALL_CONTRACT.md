# INSTALL_UNINSTALL_CONTRACT

Installation and uninstallation are separated into three scopes. Every install writes a
manifest; uninstall is manifest-driven and never guesses.

Verified by: AC-003, AC-022, AC-023, INST-001..INST-009, SMOKE-003, SMOKE-010.

## Scopes and command mapping

| Scope | What it owns | Real commands today |
|---|---|---|
| `product` | The OpenContext binary + HOME state (`~/.config/opencontext`, `~/.opencontext`) | `pipx install opencontext-cli` / `pip install` / `install.sh` / `install.ps1`; removal via `pipx uninstall` + `uninstall --full --global-state` |
| `workspace` | Per-repo state: `.opencontext/`, `opencontext.yaml`, indexes, runs, memory | `init` (wizard), `install` (quick setup); removal via `clean` or `uninstall --scope workspace --purge` |
| `agents` | Agent client config: MCP entries, instruction blocks, generated agent files | `setup [AGENT...]`; removal via `uninstall [AGENT...]` |

> Current → Target: there are no `product|workspace|agents` subcommands; the mapping above is
> the compatibility statement. `uninstall --scope {workspace,global,all}` selects state scope
> (`local` is a legacy alias for `workspace`); `--purge` deletes project artifacts; `--full`
> sweeps ledger-tracked files; `--verify` scans for residue and reports pass/fail. Target: keep
> these flags stable and document them as the scope selectors.

## Product manifest schema

```json
{
  "schema_version": 1,
  "install_method": "pipx|pip|venv|installer|manual",
  "product_version": "1.7.0",
  "created_paths": [],
  "modified_files": [],
  "shell_profile_blocks": [],
  "symlinks": [],
  "env_vars": [],
  "agent_configs": [],
  "state_paths": [],
  "timestamp": "2026-07-06T00:00:00Z"
}
```

## Workspace manifest schema

```json
{
  "schema_version": 1,
  "product_version": "1.7.0",
  "install_method": "init|install",
  "created_paths": [".opencontext", "opencontext.yaml"],
  "modified_files": [],
  "state_paths": [".opencontext/runs", ".opencontext/context-repository", ".opencontext/sdd"],
  "agent_configs": [],
  "timestamp": "2026-07-06T00:00:00Z"
}
```

> Current → Target: today `.opencontext/oc-manifest.json` exists but only records
> `app, project_root, project_id, created_by, version, created_at`. The uninstall ledger tracks
> some created files separately. Target: one manifest per scope with the fields above, written
> at install time and treated as the single source of truth for uninstall.

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

## Safety rules

- NEVER delete a path that is not registered in a manifest/ledger without explicit,
  per-path confirmation.
- Unmanaged residue is reported, not silently removed.
- `--verify` alone is read-only: scan and report, remove nothing.
- Reinstall over an existing install is idempotent and must not duplicate manifest entries
  (INST-003).
- Every destructive step is preceded by a backup when it touches user-owned files (agent
  configs, shell profiles).
