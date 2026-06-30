#!/usr/bin/env bash
# Render the README terminal demos to docs/assets/demo-*.gif from the tapes in
# docs/demos/tapes/. Fully reproducible: real OpenContext commands run against a
# real indexed repo (psf/requests), in a sandboxed HOME + XDG_CONFIG_HOME so the
# recordings never touch — or leak — your real environment.
#
# Requires: vhs (https://github.com/charmbracelet/vhs), ttyd, ffmpeg, git, and
# the `opencontext` CLI on PATH (or a repo-local .venv).
#
# Usage:  scripts/render-readme-demos.sh
# Env:    OC_DEMO_SANDBOX  override sandbox dir (default /tmp/oc-demo-sandbox)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# Prefer repo-local tool/venv if present, then fall back to PATH.
export PATH="$REPO/.tools:$REPO/.venv/bin:$PATH"

for tool in vhs ffmpeg git; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "error: '$tool' not found on PATH." >&2
    echo "  vhs: https://github.com/charmbracelet/vhs (needs ttyd + ffmpeg)" >&2
    exit 1
  }
done
OC="$(command -v opencontext)" || { echo "error: 'opencontext' not on PATH" >&2; exit 1; }

SB="${OC_DEMO_SANDBOX:-/tmp/oc-demo-sandbox}"
# Sandbox the environment: recordings must not read or write the real HOME.
# vhs uses the system Chrome, not a HOME cache, so this is safe + leak-proof.
export HOME="$SB/home"
export XDG_CONFIG_HOME="$SB/config"
rm -rf "$SB/config" "$SB/home" "$SB/install-demo"
mkdir -p "$HOME"

# Indexed project for explain / kept-out (cached clone across runs).
PROJ="$SB/requests"
if [ ! -d "$PROJ/.git" ]; then
  echo "==> cloning psf/requests (sandbox)"
  git clone --depth 1 -q https://github.com/psf/requests "$PROJ"
fi
echo "==> setting up + indexing the sandbox project (clean config each run)"
# The clone is cached across runs, but its OpenContext config is NOT — wipe it so
# a value a demo writes (e.g. security: air_gapped, which forbids LLM providers and
# breaks `explain`) never leaks into the next run's read-only demos.
rm -rf "$PROJ/opencontext.yaml" "$PROJ/.opencontext" "$PROJ/.storage"
"$OC" install --yes "$PROJ" >/dev/null 2>&1
"$OC" index "$PROJ" >/dev/null 2>&1
export OC_DEMO_EXPLAIN="$PROJ"

# Fresh, un-set-up copy so `install` has something to do on camera.
cp -r "$PROJ" "$SB/install-demo"
rm -rf "$SB/install-demo/opencontext.yaml" "$SB/install-demo/.storage" "$SB/install-demo/.opencontext"
export OC_DEMO_INSTALL="$SB/install-demo"

# Pre-configured copy so `uninstall` has agents to remove on camera. Configure
# two recognizable agents (claude-code, cursor) project-locally, off-camera.
UNINST="$SB/uninstall-demo"
rm -rf "$UNINST"
cp -r "$PROJ" "$UNINST"
"$OC" setup claude-code cursor --scope local --yes --non-interactive --root "$UNINST" >/dev/null 2>&1
export OC_DEMO_UNINSTALL="$UNINST"

echo "==> rendering tapes"
# Home (`opencontext`) and config (`opencontext config`) are now the unified Textual
# app; demo-config walks every setting through that menu (in-place selects + native
# modals), so the old per-setting cfg-* command gifs are retired as redundant.
for name in explain kept-out install menu config uninstall graph; do
  echo "  - $name"
  vhs "docs/demos/tapes/$name.tape"
done

echo "==> sizes (hard limit 10 MB, target < 5 MB)"
status=0
for name in demo-explain demo-kept-out demo-install demo-menu demo-config demo-uninstall demo-graph; do
  f="docs/assets/$name.gif"
  sz=$(stat -c%s "$f")
  printf "  %-28s %6s KiB\n" "$f" "$((sz / 1024))"
  if [ "$sz" -gt 10485760 ]; then echo "    FAIL: exceeds 10 MB" >&2; status=1; fi
done
exit "$status"
