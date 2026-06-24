# demo-uninstall.gif — the inverse of setup, shown both ways:
#   1) `uninstall --dry-run`  → preview exactly what would change, nothing removed
#   2) `uninstall`            → "About to remove…", interactive Proceed? (default No),
#                               then the removed-files report (a backup is taken first).
# Agents (claude-code, cursor) are configured off-camera by the render script into
# $OC_DEMO_UNINSTALL. Real commands, sandboxed HOME. Paced slow to follow each step.
Source "docs/demos/tapes/_common.tape"
Set Height 840
Set TypingSpeed 55ms
Output "docs/assets/demo-uninstall.gif"

Hide
Type `export PS1="$ "` Enter
Type `cd "$OC_DEMO_UNINSTALL"` Enter
Type "clear" Enter
Show

# Route 1 — dry run: see what would be removed, change nothing.
Sleep 800ms
Type "opencontext uninstall claude-code cursor --dry-run"
Sleep 500ms
Enter
Sleep 6s

# Route 2 — the real thing, interactive confirmation.
Type "opencontext uninstall claude-code cursor"
Sleep 500ms
Enter

# "About to remove OpenContext from: claude-code, cursor" + Proceed? selector.
Sleep 3500ms

# Proceed? defaults to No; move up to Yes and confirm.
Up
Sleep 1600ms
Enter

# Removed panel + per-agent files + backup note.
Sleep 6s
