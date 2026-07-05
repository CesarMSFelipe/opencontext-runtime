# Chained PR Details

## Strategy Notes

| | Stacked PRs to main | Feature Branch Chain |
|---|---|---|
| Speed | Each slice can ship in order | Full feature waits for tracker merge |
| Rollback | Revert individual main PRs | Revert/hold the whole feature branch |
| Risk | Partial behavior may land | Nothing lands until the chain completes |

## Feature Branch Chain

```
main
 └── feat/my-feature              ← tracker
      ↑ PR #1 base: feat/my-feature
      └── feat/my-feature-01-core
           ↑ PR #2 base: feat/my-feature-01-core
           └── feat/my-feature-02-shared
```

## Stacked PRs to Main

```
main ← PR 1: foundation
          └── PR 2: feature slice built on PR 1
                └── PR 3: docs/tests built on PR 2
```

## Chain Context Section

Append to the PR template:

```markdown
## Chain Context

| Field | Value |
|-------|-------|
| Chain | <feature or stack name> |
| Position | <N of total> |
| Base | `<target branch>` |
| Depends on | <PR/issue/link or "None"> |
| Review budget | <changed lines> / 400 |
```

## Commands

```bash
gh pr create --base feat/my-feature --title "feat(scope): focused slice" --body-file pr-body.md
```
