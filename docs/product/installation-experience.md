# Installation Experience: OpenContext vs Gentle-AI Pattern

OpenContext should feel similar to Gentle-AI at install time: the user chooses the AI clients they actually use, picks the desired SDD/TDD behavior, and finishes with the system ready to work. The difference is that OpenContext optimizes for minimal tokens through the local knowledge graph, context packs, memory, and per-phase budgets.

## Target UX

```bash
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
