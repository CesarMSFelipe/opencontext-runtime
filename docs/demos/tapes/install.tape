# demo-install.gif — the FULL interactive setup: detect stack, then walk every
# wizard choice (language → editor → model routing → provider) and run the
# onboarding engine (config + index + KG + SDD + agents + harness + verify).
# Real `opencontext install` (interactive, no --yes) on a fresh project copy,
# in a sandboxed HOME (no real-env mutation). Paced slow so each menu is readable.
Source "docs/demos/tapes/_common.tape"
Set Height 860
Set TypingSpeed 55ms
Output "docs/assets/demo-install.gif"

Hide
Type `export PS1="$ "` Enter
Type `cd "$OC_DEMO_INSTALL"` Enter
Type "clear" Enter
Show

Sleep 800ms
Type "opencontext install"
Sleep 700ms
Enter

# Detection + "Will configure" summary, then the wizard menus appear.
Sleep 3s

# Step 1 — Language (default: English)
Sleep 2s
Enter

# Step 2 — Editor (default: Claude Code)
Sleep 2500ms
Enter

# Step 3 — Model routing across SDD phases (default: client's model)
Sleep 2500ms
Enter

# Step 4 — LLM provider (none in sandbox → default: skip)
Sleep 2500ms
Enter

# Confirm: Proceed with setup? (default: Yes)
Sleep 2s
Enter

# Onboarding engine runs, then the Install Complete summary + next steps.
Sleep 11s
