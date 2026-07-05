# Host Support — proven-real matrix

What OpenContext actually does in each supported agent host, and what is proven
by an executable test vs. best-effort. No capability is listed as supported
without a passing test or an explicit maturity marker.

> Source of truth for capabilities: `packages/opencontext_core/opencontext_core/configurator/capability.py`.
> Proof: `tests/e2e/test_real_host_mcp.py`, `tests/e2e/test_real_host_mutation.py` (marked `real_host`),
> and `tests/core/test_mcp_agent_execute.py`. See `openspec/USER-VALIDATION-DOD.md` §Host-Integration DoD.

## Setup surface

| Host | MCP config written | Scope | Instructions | Reversible (backup + uninstall) |
|------|--------------------|-------|--------------|---------------------------------|
| claude-code | `~/.claude/mcp.json` + project `.mcp.json` (+ `~/.claude/settings.json`) | home + project | `~/.claude/CLAUDE.md` | yes |
| opencode | `~/.config/opencode/opencode.json` (+ personas in `~/.config/opencode/agents/`) | home | project `AGENTS.md` | yes |
| codex | `~/.codex/config.toml` | home | project `AGENTS.md` | yes |

`opencontext setup <host> --scope local` is the entry point; every write is wrapped in
`<!-- opencontext:instructions:start/end -->` managed markers and reversed by `opencontext uninstall`.

## Proven-real status

| Host | Config load | Live MCP handshake | Mutation contract | How proven |
|------|-------------|--------------------|-------------------|-----------|
| claude-code | ✅ proven | ✅ **Connected** (health check) | ✅ via agent_execute | `test_claude_connects_to_opencontext`; mutation loop `test_real_host_mutation.py` + `test_mcp_agent_execute.py` |
| opencode | ✅ proven | ✅ **connected** (real stdio handshake) | ✅ via agent_execute | `test_opencode_connects_to_opencontext`; same mutation proofs |
| codex | ✅ proven (`enabled`) | ⚙️ config-load only¹ | ✅ via agent_execute | `test_codex_loads_opencontext`; mutation proofs |

¹ `codex mcp list` reports the server `enabled` from config but does not perform a live health
check, so codex's listing proves config-load. The live MCP round-trip codex uses at runtime is the
same one proven by `test_real_host_mutation.py` (real `opencontext mcp` subprocess) and the
`test_mcp_agent_execute.py` protocol tests.

## Execution model (important)

None of the three hosts advertise the MCP **sampling** capability today
(`tests/docs/test_client_execution_model_truth.py` pins this). For any mutating run without a
configured provider, OpenContext returns a structured **`status: agent_execute`** handoff — the
host applies the edits with its own tools, then calls `opencontext_session_apply(kind=agent_edits)`
to complete the run with receipts. This is honest by design: OpenContext never fakes a mutation it
did not perform, and never dead-ends in a bare `needs_executor`.

- **Full model turn** (`claude -p`, `codex exec`, `opencode run`) is **best-effort**: it requires
  the host's provider credentials/network and is therefore not asserted in the credential-free test
  lane. The config-load, live handshake, and mutation-contract proofs above cover the parts that do
  not need credentials.
- When a host begins advertising `sampling`, the runtime auto-detects it per session and drives the
  run with the host's own model — no config change required.

## Running the proofs

```bash
pytest -m real_host -q            # drives the installed codex/opencode/claude binaries
pytest tests/e2e/test_real_host_mutation.py -q   # real opencontext mcp subprocess mutation loop
```

Absent host binaries skip with a reason; they never silently pass.
