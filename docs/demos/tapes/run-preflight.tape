# demo-run-preflight.gif — the guided preflight in front of `opencontext run`:
# a branded briefing (execution plan, node spine, evidence artifacts, gates,
# cost estimate, live subsystem status), then an options selector where every
# choice carries a detail card (Current / Effect / Recommended / Risk / CLI).
# The fixture repo ($OC_DEMO_RUN, built by the render script) has a real failing
# test; the sandbox has no LLM executor, so after Proceed the flow answers
# honestly — needs_executor with receipts — instead of inventing a patch.
# Taller frame + smaller font so the briefing panels stay on screen longer.
Source "docs/demos/tapes/_common.tape"
Set FontSize 14
Set Height 1000
Set TypingSpeed 45ms
Output "docs/assets/demo-run-preflight.gif"

Hide
Type `export PS1="$ " FORCE_COLOR=1 CLICOLOR_FORCE=1 RICH_FORCE_TERMINAL=1 COLORTERM=truecolor TERM=xterm-256color; unset NO_COLOR` Enter
Type `cd "$OC_DEMO_RUN"` Enter
Type "clear" Enter
Show

# The task: a genuinely failing test lives in this repo.
Sleep 800ms
Type `opencontext run "Fix the failing discount test"`
Sleep 700ms
Enter

# The briefing renders: Execution plan → How it will run → evidence spine →
# gates → cost estimate → subsystems → the Options cards + selector.
Sleep 9s

# Walk the options so each detail card's highlight is followable:
# Proceed → Change workflow → Change lane → Cancel …
Down
Sleep 1600ms
Down
Sleep 1600ms
Down
Sleep 1600ms

# … and back up to Proceed.
Up
Sleep 1300ms
Up
Sleep 1300ms
Up
Sleep 1600ms

# Proceed — the run starts. No executor is configured in the sandbox, so the
# spine answers needs_executor (honest refusal + hint), never a fake patch.
Enter
Sleep 9s
