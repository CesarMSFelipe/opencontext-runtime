# Compression

OpenContext applies compression at two levels: context packs delivered to agents, and inter-agent handoffs within the loop. All strategies preserve protected spans verbatim.

## Strategies

Four strategies, applied automatically by risk tier:

| Strategy | Tier | Reduction | What it does |
|----------|------|-----------|-------------|
| `none` | critical | 0% | Full fidelity — never compress high-risk context |
| `terse` | cheap | ~65–75% | Remove prose padding, apply substitution dictionary |
| `compact` | precise | ~50–65% | AST summaries: signatures + first docstring line, no bodies |
| `efficient` | loop output | ~70–85% | compact + terse + extended dictionary — maximum reduction |

## Automatic Selection

The `ContextPlanner` selects the strategy based on risk tier:

```python
TIER_STRATEGY = {
    "cheap":    "terse",
    "precise":  "compact",
    "critical": "none",   # never compress critical context
}
```

For `opencontext loop` output, `efficient` is the default regardless of tier.

Override:

```bash
opencontext loop --task "..." --compress none
opencontext loop --task "..." --compress terse
opencontext loop --task "..." --compress efficient
```

## How Each Strategy Works

### terse

Removes linguistic padding while preserving all technical content:

- Removes hedging words: "perhaps", "might", "I think", "basically"
- Removes filler phrases: "in order to" → "to", "it's worth noting that" →  (removed)
- Applies substitution dictionary:
  - `configuration` → `config`
  - `authentication` → `auth`
  - `database` → `db`
  - `dependencies` → `deps`
  - `returns` → `→`
  - and 40+ more

### compact

Structural compression for code:

- Extracts class and function signatures
- Preserves first docstring line
- Removes all method bodies (`...` placeholder)
- Applies terse compression to prose sections

Input:
```python
class UserService:
    def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate a user by credentials."""
        # 20 lines of implementation
        user = db.query(User).filter(...)
        ...
        return user
```

Output:
```python
class UserService:
    def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate a user by credentials..."""
    ...
```

### efficient

Maximum compression — chains compact → terse → extended dictionary:

Extended dictionary adds 30+ substitutions on top of terse:
- `function` → `fn`
- `implementation` → `impl`
- `service` → `svc`
- `connection` → `conn`
- `transaction` → `tx`
- `therefore` → `∴`
- `and` → `&`
- and more

### none

Pass-through. No modification. Used for critical-tier context where full fidelity is required.

## Protected Spans

These spans are **never modified** by any strategy:

- Fenced code blocks (` ``` `)
- Inline code (`` `backticks` ``)
- File paths (`src/auth.py`, `./config.yaml`)
- URLs
- Shell commands (`git`, `npm`, `python`, etc.)
- Version numbers (`v1.2.3`)
- Error messages and stack traces
- Test assertions
- Diffs
- UUIDs and IP addresses

## Inter-Agent Compression

Within the agentic loop, context passes between agents via `SubAgentDelegate`. Before each handoff, the context dictionary is terse-compressed:

- Text values longer than 200 characters are compressed
- Short values and structured data pass through unmodified
- Result: 60–70% fewer tokens per inter-agent handoff

## Measuring Savings

```bash
opencontext telemetry show
opencontext benchmark run
opencontext tokens report .
```

The benchmark suite reports:
- `token_reduction` — % tokens saved vs naive full-project context
- `tokens_per_successful_task` — average tokens for tasks that passed verify
- `context_precision` — % included items that were actually needed
- `context_recall` — % needed items that were included

## Configuration

```yaml
# opencontext.yaml
compression:
  strategy: terse          # default for context packs
                           # loop defaults to efficient regardless
```

## Related

- [Token Efficiency Overview](./overview.md)
- [Context Pack Builder](../architecture/context-pack-builder.md)
- [Agentic Loop](../workflows/modes.md)
