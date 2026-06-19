# Skill: oc-onboard

Initialize a project for SDD. Run this once per project before using SDD workflows.

## Steps

### 1. Discover environment
- Read package.json / pyproject.toml / go.mod / Cargo.toml
- Identify test runner (jest, vitest, pytest, go test, cargo test)
- Identify lint/typecheck commands
- Identify framework (NestJS, FastAPI, Django, Express, etc.)

### 2. Document project conventions
Create or update `.opencontext/project-conventions.md`:
- Test file naming pattern
- Module/package structure
- Code style rules
- Forbidden patterns

### 3. Verify test suite runs
Run the test suite. Document the command. If it fails, document why and stop.
DO NOT proceed with SDD on a broken baseline.

### 4. Create skill stubs if needed
If the project uses a specific framework without a local skill file,
create `skills/<framework>.skill.md` with the key conventions.

### 5. Confirm readiness
Report:
- Test command: `<cmd>`
- Tests passing: yes/no
- Typecheck command: `<cmd>` (if applicable)
- Lint command: `<cmd>` (if applicable)
- SDD ready: yes/no

## Output
A short readiness report. If not ready, explain what must be fixed first.
