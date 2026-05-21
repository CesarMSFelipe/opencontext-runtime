# Agent Hints

Agent hints provide project-specific instructions, conventions, and context to help AI agents understand your codebase better. Hints are stored in `.opencontexthints` and other supported files.

## Quick Start

```bash
# Initialize hints file
opencontext hints init

# Show combined hints
opencontext hints show

# Validate hints files
opencontext hints validate
```

## Supported Files

OpenContext discovers hints from multiple sources:

| File | Priority | Description |
|------|----------|-------------|
| `.opencontexthints` | 1 | Primary hints file (recommended) |
| `AGENTS.md` | 2 | Generic agent instructions |
| `CLAUDE.md` | 3 | Claude-specific instructions |
| `.cursor/rules/*.mdc` | 4 | Cursor rules |
| `.windsurf/rules/*.md` | 5 | Windsurf rules |

## Format

The `.opencontexthints` format uses sections with bullet points:

```
project: My Project
description: A brief description of the project

[conventions]
- Use type hints for all function signatures
- Write docstrings for public APIs
- Prefer immutable data structures
- Keep functions under 50 lines

[architecture]
- Core business logic is in the domain layer
- Infrastructure concerns are in adapters
- Use dependency injection for testability

[workflows]
- Run the full test suite before committing
- Use conventional commits for changelog generation
- Update documentation when changing public APIs

[patterns]
- Repository pattern for data access
- Strategy pattern for interchangeable algorithms
- Factory pattern for complex object creation

[warnings]
- Never commit secrets or API keys
- Don't use global mutable state
- Avoid circular dependencies between modules
```

### Sections

- **conventions**: Coding standards and style rules
- **architecture**: High-level structure and layering
- **workflows**: Development processes and checks
- **patterns**: Common design patterns used
- **warnings**: Critical things to avoid

## Integration with Context

Agent hints are automatically included when building context packs:

```python
from opencontext_core.dx.agent_hints import AgentHintsManager

manager = AgentHintsManager()
hints = manager.get_all_hints()
context = manager.to_context_string(hints)

# Include in prompt
prompt = f"""{context}

Now, review this code:
```python
def authenticate_user(username, password):
    ...
```
"""
```

## Best Practices

1. **Be specific**: "Use type hints" is better than "Write good code"
2. **Be concise**: Agents have limited context windows
3. **Prioritize**: Put most important rules first in each section
4. **Keep updated**: Refresh when architecture changes
5. **Version control**: Commit `.opencontexthints` with your code

## Programmatic Usage

```python
from opencontext_core.dx.agent_hints import AgentHintsManager

manager = AgentHintsManager(".")

# Discover all hints files
files = manager.discover_hints()
print(f"Found hints in: {files}")

# Get combined hints
hints = manager.get_all_hints()
print(f"Project: {hints.project_name}")
print(f"Conventions: {len(hints.conventions)}")

# Generate context string
context = manager.to_context_string(hints)
```
