# demo-menu.gif — the unified Textual home: one branded app (logo + live KG header +
# every top-level action), the same chrome every screen shares. `opencontext` with
# no args. Paced slow so the highlight is followable.
Source "docs/demos/tapes/_common.tape"
Set Height 720
Set TypingSpeed 55ms
Output "docs/assets/demo-menu.gif"

Hide
Type `export PS1="$ "` Enter
Type `cd "$OC_DEMO_EXPLAIN"` Enter
Type "clear" Enter
Show

Sleep 800ms
Type "opencontext"
Sleep 500ms
Enter

# Textual home renders: BrandBar + KG status line + the action list + footer.
Sleep 3500ms

# Walk the actions.
Down
Sleep 1300ms
Down
Sleep 1300ms
Down
Sleep 1300ms
Down
Sleep 1300ms
Down
Sleep 1300ms
Up
Sleep 1500ms

# Linger on the screen so the final frame is readable (no blank exit frame).
Sleep 4500ms
