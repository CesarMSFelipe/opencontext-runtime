# Implementation Matrix (Implemented vs Planned)

| Area | Implemented now | Planned / partial |
|---|---|---|
| Security modes | developer/private_project/enterprise/air_gapped config and policy checks | deeper network/tool transport hardening per mode |
| Provider policy | allow/deny, classification allowlists, redaction/private endpoint/training/retention checks | provider attestation and signed compliance metadata |
| Prompt injection | scanner and untrusted-context rendering | richer detectors and confidence-based policy actions |
| Secret scanning | scanner + redaction in indexing, prompt sinks, output surfaces, and exact-cache writes | broader pattern catalog and external scanner adapters |
| PII/DLP | basic PII scanner integrated into prompt sink-guard | enterprise DLP adapters and policy routing |
| Retrieval | keyword/path/symbol hybrid, static dependency graph extraction, local deterministic embedding records, and cross-project graph tunnel storage | production vector backends and learned reranker adapters outside core |
| Technology profiles | Core profile protocol + generic fallback; broad first-party catalog across web, mobile, backend, data, DevOps/IaC, monorepo, database, and platform stacks | independent per-profile packages |
| Context optimization | budgeting/ranking/packing/compression/protected spans/content routing/compact serializers/output budgets | higher-fidelity structured compression |
| Memory | local context repository, progressive disclosure, multi-signal memory search, pinning, harvesting, novelty gate, temporal graph, context DAG, expansion, and GC scaffold | external memory backend adapters and stronger conflict resolution |
| Workflow engine | YAML workflows, traceable steps, SDD-style safe steps, and controlled harness preflight planner | checkpoint store and resumable execution |
| Context/action modes | Ask/plan/architect/act/review/audit/debug/implement-pack/validate/orchestrate/enterprise/air-gapped/custom enum and CLI mode choices | mode-specific output contracts and workflow step presets |
| Permissioned action layer | Typed action classes with allow/ask/deny defaults; writes/network/MCP denied by default; safe commands/tests/linters require approval | approved command execution and sandbox boundary |
| Tool runtime | registry + deny-by-default policy + strict-mode explicit permission + read/write/network permission pipeline + untrusted/sanitized outputs | MCP adapter execution implementation |
| CLI/API scaffold surface | harness run, provider simulate, reports, release evidence, Drupal test planning, and matching API scaffolds | full implementations behind policies |
| Observability | local JSON traces + sanitizer | optional OTel exporter |
| Evaluation | eval models + basic evaluator | security regression suites and leakage benchmarks |
