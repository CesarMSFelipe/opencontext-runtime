# Git Context

OpenContext enriches knowledge graph queries with git metadata including authorship, change history, and blame information. This provides additional context when building AI task context or analyzing impact.

## Quick Start

```bash
# Show repository stats
opencontext git status

# Show file history
opencontext git history src/auth.py

# Show recent changes
opencontext git recent --days 7 --max-commits 20

# Show blame for lines
opencontext git blame src/auth.py --start 10 --end 25
```

## Features

### Repository Statistics

Get high-level repository metrics:

```bash
opencontext git status
```

Output:
```json
{
  "available": true,
  "total_commits": 1523,
  "contributors": 8,
  "branches": 12
}
```

### File History

Get detailed git metadata for a specific file:

```bash
opencontext git history src/auth.py
```

Includes:
- Last modified date and author
- Total commit count for the file
- Lines added/removed
- Top contributors

### Recent Changes

View recent commits with changed files:

```bash
opencontext git recent --days 14 --max-commits 50
```

### Line Blame

Trace authorship for specific lines:

```bash
opencontext git blame src/auth.py --start 50 --end 75
```

## Integration with Knowledge Graph

Git context automatically enriches knowledge graph queries:

```python
from opencontext_core.indexing.git_context import GitContextProvider
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

# Build knowledge graph
kg = KnowledgeGraph()
kg.index_project(".")

# Enrich with git context
provider = GitContextProvider(".")
enriched = provider.enrich_context(["src/auth.py", "src/models.py"])

# enriched now contains git metadata for each file
print(enriched["src/auth.py"]["last_author"])
print(enriched["src/auth.py"]["commit_count"])
```

## Use Cases

1. **Impact Analysis**: "Who should review this change?" → Check top authors
2. **Onboarding**: "Who knows this code?" → Check last author and contributors
3. **Context Building**: "How recently was this modified?" → Include recency in ranking
4. **Code Review**: "What's the history of this function?" → Check blame

## Programmatic Usage

```python
from opencontext_core.indexing.git_context import GitContextProvider

provider = GitContextProvider(".")

if provider.available:
    # Get file info
    info = provider.get_file_info("src/auth.py")
    print(f"Commits: {info.commit_count}")
    print(f"Last author: {info.last_author}")

    # Get recent changes
    diffs = provider.get_recent_changes(days=7, max_commits=20)
    for diff in diffs:
        print(f"{diff.commit_hash}: {diff.message}")

    # Get blame
    lines = provider.get_blame_for_symbol("src/auth.py", 10, 20)
    for line in lines:
        print(f"{line['author']}: {line['code']}")
```
