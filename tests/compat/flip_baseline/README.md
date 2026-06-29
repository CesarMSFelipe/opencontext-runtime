# Flip baseline (committed migration evidence)

This directory holds the **tracked, committed** baseline of accepted vNext
`FlipEvidence` bundles (`<subsystem>.json`). It exists because the runtime flip
directory `.opencontext/flips/` is **gitignored** (it is rewritten by every
`opencontext release acceptance` run, so its diffs are unstable and unreviewable).
A committed baseline makes the migration evidence **deterministic and reproducible on
a fresh CI checkout**.

## How it is read

`compat/flip_evidence.py:read_flip_bundles(root)` reads the **union** of:

1. this committed baseline (`tests/compat/flip_baseline/`), and
2. the runtime dir (`.opencontext/flips/`),

with the **runtime path winning** on a per-subsystem conflict. So:

- **CI / fresh checkout** — only the committed baseline is present; its accepted
  bundles are visible to both the CL-005 contract test
  (`tests/compat/test_compat_flags.py`) and `release acceptance`.
- **Local development** — a fresh `release acceptance` run writes
  `.opencontext/flips/`, which overrides the baseline for that subsystem, so local
  evidence always reflects the current working tree.

Because the read is a union, **no CI copy/seed step is required** — the committed
baseline is read directly. (Earlier designs proposed
`cp tests/compat/flip_baseline/*.json .opencontext/flips/` before `release
acceptance`; the union read makes that step unnecessary.)

## Graceful fallback

When neither directory contains bundles (an empty baseline + no runtime dir, e.g. the
current state before any subsystem has been flipped), `read_flip_bundles()` returns
`[]`. The CL-005 test then asserts **every** `*_enabled` flag defaults `False` and
passes — it never errors.

## Current state

Empty (only `.gitkeep` + this README). No accepted bundles exist yet: the Phase 8 flip
run produced **reverted** bundles only (auto-reverted on the CL-005 benchmark). The
flip-execution phase (VDM-003) will copy the accepted `<subsystem>.json` bundles here
once the flips are accepted. Until then the legacy default-`False` contract holds for
all subsystems.
