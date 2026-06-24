# demo-config.gif — the COMPLETE configuration walkthrough, all in one branded
# Textual app. The 3-column Miller menu drives every setting: simple ones are
# picked in place (the ✓ moves, a flash confirms); richer ones open a native modal
# screen (toggles / typed value / two-step pick) that shares the same chrome, then
# return to the menu. Real `opencontext config` against the indexed sandbox repo.
Source "docs/demos/tapes/_common.tape"
Set Height 760
Set TypingSpeed 60ms
Output "docs/assets/demo-config.gif"

Hide
Type `export PS1="$ "` Enter
Type `cd "$OC_DEMO_EXPLAIN"` Enter
Type "clear" Enter
Show

Sleep 800ms
Type "opencontext config"
Sleep 500ms
Enter

# MegaMenu renders: Category · Setting · Options + footer.
Sleep 3500ms

# Tour the categories, settle on Settings, drill in.
Down
Sleep 1200ms
Down
Sleep 1200ms
Up
Sleep 1200ms
Right
Sleep 1600ms

# 1 — Security (in-place select): drill to modes, pick one, apply, back.
Right
Sleep 1500ms
Down
Sleep 900ms
Down
Sleep 1200ms
Enter
Sleep 2200ms
Left
Sleep 1200ms

# 2 — Features (native toggle modal): toggle one off, save, return.
Down
Sleep 900ms
Enter
Sleep 2600ms
Down
Sleep 1100ms
Space
Sleep 1300ms
Type "s"
Sleep 2200ms

# 3 — Token budgets (native input modal): replace the value.
Down
Sleep 900ms
Enter
Sleep 2400ms
Backspace
Backspace
Backspace
Backspace
Backspace
Sleep 600ms
Type "8000"
Sleep 1100ms
Enter
Sleep 2200ms

# 4 — Providers & models (native two-step modal): provider → model.
Down
Sleep 900ms
Enter
Sleep 2400ms
Down
Sleep 1100ms
Enter
Sleep 1600ms
Down
Sleep 1100ms
Enter
Sleep 2200ms

# 5 — Agent integrations (native toggle modal).
Down
Sleep 900ms
Enter
Sleep 2400ms
Space
Sleep 1000ms
Down
Sleep 900ms
Space
Sleep 1200ms
Type "s"
Sleep 2200ms

# 6 — Plugins (native toggle modal): update prefs + any plugins.
Down
Sleep 900ms
Enter
Sleep 3200ms
Down
Sleep 1000ms
Space
Sleep 1300ms
Type "s"
Sleep 2200ms

# 7 — Memory backend (native single-pick modal).
Down
Sleep 900ms
Enter
Sleep 2400ms
Down
Sleep 900ms
Down
Sleep 1100ms
Enter
Sleep 2200ms

# 8 — Language (in-place select).
Down
Sleep 900ms
Right
Sleep 1400ms
Down
Sleep 1100ms
Enter
Sleep 2000ms
Left
Sleep 1100ms

# 9 — SDD model profile (in-place select).
Down
Sleep 900ms
Right
Sleep 1300ms
Down
Sleep 1100ms
Enter
Sleep 2000ms
Left
Sleep 1100ms

# 10 — TDD mode (in-place select).
Down
Sleep 900ms
Right
Sleep 1300ms
Down
Sleep 1100ms
Enter
Sleep 2000ms
Left
Sleep 1200ms

# Quit.
Type "q"
Sleep 1500ms
