# Skill: fix

Disciplined debugging workflow. Never guess. Never brute-force.

## Trigger
- A test is failing unexpectedly
- A bug is reported
- A regression appeared

## Workflow

### 1. Reproduce
Run the exact failing command. Capture full output. Do NOT proceed without a reproducible failure.

### 2. Hypothesize
State ONE specific hypothesis: "The failure is caused by X because Y."
Do NOT try multiple things at once.

### 3. Instrument
Add minimal logging/assertions to validate or refute the hypothesis.
Run again. Read the output.

### 4. Fix
Write the minimal code change that fixes the root cause.
Do NOT fix symptoms.

### 5. Regression test
Write a test that would have caught this bug.
Verify it was RED before the fix, GREEN after.

### 6. Cleanup
Remove instrumentation. Verify full suite still passes.

## Rules
- One hypothesis at a time.
- No fix without a reproduction.
- No close without a regression test.
- If hypothesis is wrong after instrument step, form a new hypothesis — do NOT start guessing.
