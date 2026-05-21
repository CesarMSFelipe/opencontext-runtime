# Windsurf

## Purpose
Windsurf uses workflows for task automation. OpenContext generates
a workflow file with plan/code mode instructions.

## Setup

```bash
opencontext onboard
opencontext agent init --target windsurf
```

This creates `~/.windsurf/workflows/opencontext.md`.

## Available Commands

```bash
# Code exploration
opencontext pack . --query "Review auth" --mode plan --copy
opencontext index .
opencontext inspect repomap

# Health
opencontext verify
opencontext update
opencontext upgrade

# Plugins
opencontext plugin search
opencontext plugin install <name>
opencontext plugin info <name>

# Config
opencontext config show
opencontext config reconfigure plugins
```

## Related Commands

```bash
opencontext agent init --target windsurf
opencontext agent-context "Review access control" --target windsurf --copy
```
