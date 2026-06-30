# demo-graph.gif — the knowledge-graph EXPLORER, two views (Tab toggles):
#   List  — focus node + what it calls (→) / what calls it (←), as a list.
#   Graph — a local diagram: focus in the middle, callers left, callees right.
# ↑↓ select · Enter walks into a neighbor (drill) · Backspace back · esc close.
Source "docs/demos/tapes/_common.tape"
Set Height 720
Output "docs/assets/demo-graph.gif"

Hide
Type `export PS1="$ "` Enter
Type `cd "$OC_DEMO_EXPLAIN"` Enter
Type "clear" Enter
Show

Sleep 800ms
Type "opencontext"
Sleep 400ms
Enter
Sleep 3000ms
Type "g"
Sleep 3500ms
# Switch to the graphical view.
Tab
Sleep 3800ms
# Move the cursor between neighbors in the graph view.
Down
Sleep 1300ms
Down
Sleep 1300ms
# Walk into the highlighted neighbor (drill a level deeper).
Enter
Sleep 3500ms
# Back out, then back to the list view.
Backspace
Sleep 2600ms
Tab
Sleep 2600ms
