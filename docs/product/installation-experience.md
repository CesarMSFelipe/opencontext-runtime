# Installation Experience

At install time, the user chooses the AI clients they actually use, picks the desired SDD/TDD behavior, and finishes with the system ready to work. OpenContext optimizes for minimal tokens through the local knowledge graph, context packs, memory, and per-phase budgets.

Running `opencontext` with no arguments launches an interactive TUI menu with 10 options.

## Target UX

```bash
# Quick launch — TUI menu
opencontext

# Direct setup
opencontext setup --preset full --agent opencode --agent cursor --tdd ask --root . --max-tokens 3000
```

After the setup wizard finishes, the project should already have:

- selected client integrations configured globally where supported;
- project-local agent instruction files;
- `.opencontext/sdd/context.json` and `.opencontext/sdd/testing.md`;
- a fresh knowledge graph index;
- SDD phase guidance and TDD preference available to agents;
- token budgets per SDD phase.

No second install/configuration step should be required.

## Re-run detection

If `opencontext install` detects that the project is already set up (`.opencontext/sdd/context.json` exists),
it asks "Re-run setup?" defaulting to No. This prevents accidental reconfiguration.

## Smart config default

`opencontext config` without a subcommand runs the interactive wizard directly instead of erroring.
`opencontext config wizard` also works for explicit invocation.

## TDD Modes

| Mode | Behavior |
|---|---|
| `ask` | Default. The agent asks per change whether to use TDD and recommends yes when a test harness exists. |
| `strict` | The agent writes/updates the closest failing test before implementation whenever a harness exists. |
| `off` | SDD still works, but TDD is optional and should not block apply. |

## Token-saving contract

Agents installed by OpenContext should:

1. use the knowledge graph/MCP context before broad reads;
2. use compact per-phase `opencontext pack` budgets;
3. preserve omitted-context reasons and trace ids;
4. use memory for decisions/patterns instead of restating long history;
5. run impact checks before edits;
6. run focused tests before broad checks.

## Implemented increment

- `opencontext setup` accepts repeated or comma-separated `--agent` values.
- `opencontext setup` accepts `--tdd ask|strict|off`, `--root`, and `--max-tokens`.
- Setup writes project-local agent files for each selected client.
- Setup installs global client configuration for selected agents when graph/MCP components are enabled.
- Setup writes SDD/TDD artifacts and indexes the project during the same flow.
