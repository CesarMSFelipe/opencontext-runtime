# demo-uninstall.gif — the inverse of setup, shown both ways:
#   1) `uninstall --dry-run`  → preview exactly what would change, nothing removed
#   2) `uninstall`            → the branded wizard frame: Step 1/2 scope selector
#                               (workspace / global / full, each with a detail card),
#                               then Step 2/2 confirm (default No) and the
#                               removed-files report (a backup is taken first).
# Agents (claude-code, cursor) are configured off-camera by the render script into
# $OC_DEMO_UNINSTALL. Real commands, sandboxed HOME. Paced slow to follow each step.
Source "docs/demos/tapes/_common.tape"
Set Height 840
Set TypingSpeed 55ms
Output "docs/assets/demo-uninstall.gif"

Hide
Type `export PS1="$ " FORCE_COLOR=1 CLICOLOR_FORCE=1 RICH_FORCE_TERMINAL=1 COLORTERM=truecolor TERM=xterm-256color; unset NO_COLOR` Enter
Type `cd "$OC_DEMO_UNINSTALL"` Enter
Type "clear" Enter
Show

# Route 1 — dry run: see what would be removed, change nothing.
Sleep 800ms
Type "opencontext uninstall claude-code cursor --dry-run"
Sleep 500ms
Enter
Sleep 6s

# Route 2 — the real thing, interactive scope wizard + confirmation.
Type "opencontext uninstall claude-code cursor"
Sleep 500ms
Enter

# Step 1/2 — the wizard frame (logo + status line + detail card), then the scope
# selector: Workspace / Global / Full. Default (Workspace) is right here.
Sleep 4s
Enter

# Step 2/2 — confirm removal frame + "About to remove…" + Proceed? selector.
Sleep 4s

# Proceed? defaults to No; move up to Yes and confirm.
Up
Sleep 2s
Enter

# Removed panel + per-agent files + backup note.
Sleep 6s
