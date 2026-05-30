---
title: OpenContext Runtime
description: Context engineering runtime for AI coding agents. Up to 96% token reduction.
hide:
  - navigation
  - feedback
  - toc
---

# Your AI agent reads the whole project.<br>OpenContext sends only what matters.

<div class="hero-eyebrow">v1.0.1 — Now on PyPI</div>

<div class="hero-sub">Context engineering runtime for AI coding agents. Index your project into a queryable knowledge graph. Send only relevant, ranked, redacted context — up to 96% token reduction.</div>

<div class="hero-actions">
  <a href="pip/" class="btn btn-primary">
    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path d="M6 2l.6.6M12 2l-.6.6M18 2l-.6.6M6 22l-.6-.6M12 22l.6-.6M18 22l.6-.6M2 12h2M20 12h2M12 2v2M12 20v2"/></svg>
    pip install opencontext-cli
  </a>
  <a href="https://github.com/CesarMSFelipe/OpenContext-Runtime" class="btn btn-secondary">
    <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.48C19.138 20.193 22 16.418 22 12.017 22 6.484 17.522 2 12 2z"/></svg>
    Star on GitHub
  </a>
</div>

---

## By the numbers

| | |
|---|---|
| **96%** token reduction | vs sending the full project — verified via benchmark |
| **13+** agents supported | OpenCode, Cursor, Claude Code, Windsurf, and more |
| **Offline** | No API keys needed — the entire stack runs locally |

---

## Features

<div class="features">

### 🔍 Knowledge Graph
Indexes call chains, imports, and framework routes into a queryable SQLite graph. No external services, no API keys.

### 📦 Context Packs
Task-specific, redacted, ranked, and budgeted before every LLM call. Only what matters gets sent.

### 🛡️ Privacy & Security
Secrets redacted automatically. Governance with audit trails. Air-gapped mode supported.

### 🔗 13+ Agents
OpenCode, Cursor, Claude Code, Windsurf, Kilo Code, and more — auto-configured on install.

### 📐 SDD Workflow
Spec-Driven Development with built-in TDD, phase governance, and traceable decisions.

### ⚡ Works Offline
The entire stack runs locally. No external APIs, no network required after setup.

</div>

---

## Quick Start

```bash
pip install opencontext-cli
cd your-project
opencontext setup --preset context-first
```

```bash
opencontext pack . --query "How does auth work?" --copy
```

Want the full agent workflow?

```bash
opencontext setup --preset full --agent opencode
```

MCP tools, per-phase budgets, memory, governance — the runtime handles the rest.

---

## Setup Presets

Modular by design. Start small and add capabilities as you need them.

| Preset | Description | Agents |
|--------|-------------|--------|
| `context-first` | KG + retrieval + git. No agents. Fast, offline. | No |
| `full` | Everything — KG, learning, governance, MCP, plugins. | Yes |
| `enterprise` | Governance, audit, team policies with full KG. | No |
| `air-gapped` | Completely offline — no network features. | No |

---

## Try it on your next project

862 tests passing. Works offline. No API keys needed.

→ [GitHub](https://github.com/CesarMSFelipe/OpenContext-Runtime)  
→ [PyPI](https://pypi.org/project/opencontext-cli/)