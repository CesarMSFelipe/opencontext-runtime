# demo-kept-out.gif — honesty of the budget: excluded items are named with a reason,
# never silently dropped. Real `opencontext explain --max-tokens` against psf/requests.
Source "docs/demos/tapes/_common.tape"
Output "docs/assets/demo-kept-out.gif"

Hide
Type `export PS1="$ " FORCE_COLOR=1 CLICOLOR_FORCE=1 RICH_FORCE_TERMINAL=1 COLORTERM=truecolor TERM=xterm-256color; unset NO_COLOR` Enter
Type `cd "$OC_DEMO_EXPLAIN"` Enter
Type "clear" Enter
Show

Sleep 600ms
Type `opencontext explain "request session adapters and models" --max-tokens 1500`
Sleep 500ms
Enter
Sleep 4500ms
