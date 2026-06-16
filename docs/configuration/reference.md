# Configuration Reference

This reference documents the top-level OpenContext configuration fields. The runtime deep-merges user YAML onto safe defaults from `opencontext_core.config.default_config_data()`.

| Field | Purpose | Default | Safe Value | Risky Value | Status | Related Command |
|---|---|---|---|---|---|---|
| `security` | Runtime posture, fail-closed behavior, default classification | private project | `mode: private_project`, `fail_closed: true` | external providers on without policy | Implemented | `opencontext doctor security` |
| `providers` | Global external provider switch | external off | `external_enabled: false` | `true` without provider policy | Implemented | `opencontext provider simulate` |
| `provider_policies` | Per-provider classification and retention rules | mock/local allow, external deny | require redaction/ZDR for external | training opt-in for private code | Implemented | `opencontext provider simulate` |
| `tools` | Native and MCP execution flags | disabled | `native.enabled: false`, `mcp.enabled: false` | write/network/MCP enabled broadly | Implemented boundary | `opencontext doctor tools` |
| `mcp` | MCP adapter policy under `tools.mcp` | disabled | disabled with allowlist required | stdio/network without sandbox | Scaffolded boundary | `opencontext doctor tools` |
| `traces` | Raw vs redacted context trace persistence | raw off, redacted on | `store_raw_context: false` | raw trace context | Implemented | `opencontext trace last` |
| `cache` | Exact and semantic cache policy | exact on, semantic off | exact local cache | semantic cache for confidential data | Interface implemented, semantic scaffolded | `opencontext cache plan` |
| `memory` | Progressive memory and harvesting policy | enabled, harvest off, approval on | `store_raw: false` | auto-harvest raw content | Implemented/scaffolded | `opencontext memory init` |
| `output` | Output mode and token cap | concise, 1500 | preserve warnings/paths/numbers | unlimited verbose output | Implemented | `opencontext ask --output-mode technical_terse` |
| `context` | Input budget, sections, ranking, compression | 12000 max input | reserve output and section budgets | no output reserve | Implemented | `opencontext pack` |
| `compression` | Global compression policy | adaptive protected spans | protected spans on | lossy code compression | Implemented/scaffolded | `opencontext doctor tokens` |
| `repo_map` | Repo map generation and symbol inclusion | enabled | include symbols, token cap | dumping raw files | Implemented | `opencontext inspect repomap` |
| `retrieval` | Retrieval and rerank sizes | hybrid top_k 20 | lower top_k for speed | excessive top_k | Implemented | `opencontext pack` |
| `workflows` | Named step sequences | code_assistant | local-safe steps | steps that bypass policy | Implemented/scaffolded | `opencontext workflows list` |
| `profiles` | Technology profile metadata | empty | first-party profile hints | framework code in core | Scaffolded | `opencontext init --template drupal` |
| `server` | API server defaults | disabled, 127.0.0.1:8000 | local bind | public bind without auth | Thin adapter | `uvicorn opencontext_api.main:app` |
| `egress` | Output/network/export policy | network deny | redacted clipboard/file export | webhook/network allow | Scaffolded | `opencontext prompt export` |
| `provider_cache` | Provider cache planning | explicit disabled | local planning only | provider cache without policy | Scaffolded | `opencontext cache plan` |
| `token_budgets` | Workflow input/output budgets | ask/plan/review/audit defaults | workflow-specific caps | no output cap | Scaffolded policy | `opencontext report cost` |
| `latency` | Workflow latency caps | ask 20s, plan 60s, audit 120s | local/cache-first | expensive model first | Scaffolded policy | `opencontext harness run` |

Example safe output policy:

```yaml
output:
  mode: concise
  max_output_tokens: 1500
  preserve: [code, commands, paths, symbols, warnings, numbers]
```

Example risky value to avoid:

```yaml
traces:
  store_raw_context: true
```

Raw trace context can contain private code or secrets and is disabled by default.
