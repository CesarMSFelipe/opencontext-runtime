# demo-install.gif — the FULL interactive setup: detect stack, then walk every
# wizard choice (language → editor → model routing → provider) and run the
# onboarding engine (config + index + KG + SDD + agents + harness + verify).
# Every step renders the shared brand frame: compact logo + live status line +
# Step N/4 dots + a detail card (Current / Effect / Recommended / Risk / CLI).
# Real `opencontext install` (interactive, no --yes) on a fresh project copy,
# in a sandboxed HOME (no real-env mutation). Paced slow so each frame is readable.
Source "docs/demos/tapes/_common.tape"
Set Height 860
Set TypingSpeed 55ms
Output "docs/assets/demo-install.gif"

Hide
Type `export PS1="$ " FORCE_COLOR=1 CLICOLOR_FORCE=1 RICH_FORCE_TERMINAL=1 COLORTERM=truecolor TERM=xterm-256color; unset NO_COLOR` Enter
Type `cd "$OC_DEMO_INSTALL"` Enter
Type "clear" Enter
Show

Sleep 800ms
Type "opencontext install"
Sleep 700ms
Enter

# Detection + "Will configure" summary, then the framed wizard steps appear.
Sleep 3s

# Step 1/4 — Interface language (framed, default: English)
Sleep 2500ms
Enter

# Step 2/4 — AI coding editor (framed, default: Claude Code)
Sleep 3s
Enter

# Step 3/4 — Model routing across SDD phases (framed, default: client's model)
Sleep 3s
Enter

# Step 4/4 — LLM provider key (none in sandbox → default: skip)
Sleep 3s
Enter

# Confirm: Proceed with setup? (default: Yes)
Sleep 2s
Enter

# Onboarding engine runs, then the Install Complete summary + next steps.
Sleep 11s
