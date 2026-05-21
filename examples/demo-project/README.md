# OpenContext Demo Project

A sample project to try OpenContext features.

## Quick Start

```bash
cd examples/demo-project
opencontext onboard .
opencontext index .
opencontext pack . --query "Explain authentication"
opencontext knowledge-graph search "authenticate"
```

## Project Structure

```
demo-project/
├── src/
│   ├── auth.py          # Authentication module
│   ├── models.py        # Data models
│   ├── services.py      # Business logic
│   └── main.py          # Entry point
├── tests/
│   └── test_auth.py     # Tests
└── README.md
```

## Try These Commands

```bash
# Search for symbols
opencontext knowledge-graph search "User"

# Find callers
opencontext knowledge-graph callers "authenticate_user"

# Analyze impact
opencontext knowledge-graph impact "UserService"

# Git context
opencontext git status
opencontext git history src/auth.py

# CI checks
opencontext ci-check init
opencontext ci-check run

# Agent hints
opencontext hints init
opencontext hints show
```
