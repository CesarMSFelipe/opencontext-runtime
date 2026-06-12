# Spec: Agent Setup OpenContext Profile

## ADDED Requirements

### Requirement: OpenContext SDD/TDD Profile

The system MUST provide a first-class `opencontext` orchestration profile for agent setup.

#### Scenario: Codex setup uses OpenContext profile

- GIVEN setup is run with agent `codex`
- WHEN SDD context is written
- THEN `orchestrator_profiles.codex` MUST be `opencontext`
- AND the generated instructions MUST describe Codex as direct, low-verbosity, and context-pack-first.

#### Scenario: OpenCode-family setup uses OpenContext profile

- GIVEN setup is run with agent `opencode` or an OpenCode-compatible client
- WHEN SDD context is written
- THEN the client profile MUST be `opencontext`
- AND the generated instructions MUST preserve OpenContext governance instead of hardcoding agentic workflow tool semantics.

### Requirement: Preinstalled TDD Rules

The system MUST persist TDD behavior in generated SDD context.

#### Scenario: Strict TDD project

- GIVEN a test harness is detected and setup uses `--tdd strict`
- WHEN context is generated
- THEN `tdd_mode` MUST be `strict`
- AND apply-phase instructions MUST require test-first implementation.

### Requirement: SDD Control Modes

The system MUST persist execution and artifact persistence modes for guided SDD.

#### Scenario: Default guided setup

- GIVEN setup is run non-interactively
- WHEN SDD context is generated
- THEN `execution_mode` SHOULD default to `auto`
- AND `artifact_mode` SHOULD default to `hybrid`
- AND agents MUST be told to ask only when risk or missing configuration requires it.

#### Scenario: Configurable setup

- GIVEN a user chooses different SDD modes
- WHEN setup is run
- THEN the selected modes MUST be represented in project-local context and human-readable testing docs.
