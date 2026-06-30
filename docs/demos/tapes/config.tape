# demo-config.gif — the unified configuration TUI (3-column Miller menu). Shows
# the new OC Flow mode setting, then switches the UI language to Spanish LIVE
# (the whole menu re-renders in Spanish without a relaunch). Real `opencontext
# config` against the indexed sandbox repo.
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
# 3-column menu renders (Category | Setting | Options), categories focused.
Sleep 3500ms

# Agentic workflow -> the new OC Flow mode.
Down
Sleep 1100ms
Down
Sleep 1400ms
Right
Sleep 1300ms
Down
Sleep 1000ms
Down
Sleep 1500ms
Right
Sleep 2200ms
Left
Sleep 1000ms
Left
Sleep 1000ms

# Runtime -> Language -> Espanol (the whole menu flips to Spanish, live).
Up
Sleep 1200ms
Right
Sleep 1300ms
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 1300ms
Right
Sleep 1300ms
Down
Sleep 1100ms
Enter
# Menu re-renders in Spanish. Linger so it is readable.
Sleep 5000ms
