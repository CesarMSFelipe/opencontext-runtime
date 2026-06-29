# OpenContext Provider Gateway & Model Routing Architecture
## Version 1.0 (Draft)
### Document ID
OC-PROVIDERS-001

# Purpose

This document defines the provider abstraction used by OpenContext.

Providers (LLMs, embeddings, rerankers and future AI services) are infrastructure components behind a stable gateway. The Runtime never depends directly on a vendor SDK.

# Principles

1. Provider-agnostic Runtime.
2. Structured outputs first.
3. Capability-based routing.
4. Cost-aware selection.
5. Policy-governed requests.
6. Automatic fallback.
7. Observable provider usage.
8. Pluggable adapters.

# Provider Types

- Chat models
- Reasoning models
- Embedding models
- Rerankers
- OCR
- Speech
- Image generation (optional)

# Gateway

```text
Runtime
  -> Provider Gateway
      -> Routing Engine
      -> Policy Filter
      -> Prompt Builder
      -> Provider Adapter
```

# Routing Inputs

- workflow
- workflow node
- skill
- token budget
- latency target
- confidence target
- required capabilities
- profile

# Routing Strategies

- cheapest
- fastest
- balanced
- highest_quality
- local_first
- enterprise

# Capability Model

Providers advertise:

- structured_output
- tool_use
- long_context
- reasoning
- streaming
- vision
- embeddings

Runtime selects providers by capability rather than vendor.

# Fallback

Fallback triggers:

- timeout
- quota
- provider error
- unsupported capability

Fallback must preserve contracts and emit receipts.

# Prompt Pipeline

Before provider invocation:

1. Policy redaction
2. Context budget
3. Memory injection
4. KG references
5. Compression
6. Contract validation

# Cost Tracking

Each provider call records:

- input tokens
- output tokens
- latency
- retries
- estimated cost
- model
- routing reason

# Configuration

```yaml
providers:
  strategy: balanced

  routing:
    chat: auto
    reasoning: auto
    embedding: auto

  fallback: true
  retry_limit: 2
  streaming: true
```

# Events

- provider.selected
- provider.called
- provider.completed
- provider.failed
- provider.fallback
- provider.timeout

# Receipts

- provider-selection
- provider-call
- fallback
- cost

# Migration

Current provider integrations migrate behind ProviderGateway adapters without changing Runtime behaviour.

# Definition of Done

- ProviderGateway exists.
- Vendor adapters implement common interface.
- Routing is capability-based.
- Fallback works.
- Costs are tracked.
- Policies apply before every request.

# Final Statement

Providers are replaceable infrastructure.

The Runtime should know what capabilities it needs, never which vendor implements them.
