# demo-explain.gif — the core move: one call returns a verified, call-graph-ranked pack.
# Real `opencontext explain` against a real indexed repo (psf/requests).
# Sandbox dir + PATH come from the render script via $OC_DEMO_EXPLAIN (no hardcoded paths).
Source "docs/demos/tapes/_common.tape"
Output "docs/assets/demo-explain.gif"

Hide
Type `export PS1="$ " FORCE_COLOR=1 CLICOLOR_FORCE=1 RICH_FORCE_TERMINAL=1 COLORTERM=truecolor TERM=xterm-256color; unset NO_COLOR` Enter
Type `cd "$OC_DEMO_EXPLAIN"` Enter
Type "clear" Enter
Show

Sleep 600ms
Type `opencontext explain "how does authentication work"`
Sleep 500ms
Enter
Sleep 11s
