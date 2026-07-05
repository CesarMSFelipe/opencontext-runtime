#!/usr/bin/env bash
# Build a clean release source ZIP: tracked files only, no dev state.
# Usage: scripts/build_release_zip.sh [output.zip]
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

version="$(./.venv/bin/opencontext --version 2>/dev/null | awk '{print $NF}' || echo dev)"
out="${1:-dist/opencontext-runtime-${version}.zip}"
mkdir -p "$(dirname "$out")"
rm -f "$out"

# git archive = tracked files only: excludes .git, venvs, caches,
# .opencontext/.storage/.sdd and every other untracked dev dir.
git archive --format=zip --output "$out" HEAD
# .claude/ is tracked for repo dogfooding but is not product source.
zip -qd "$out" ".claude/*" >/dev/null 2>&1 || true

entries="$(unzip -l "$out" | tail -1 | awk '{print $2}')"
echo "release zip: $out (${entries} entries)"

# Guard: none of the dev-state dirs may appear inside the zip.
if unzip -l "$out" | awk '{print $4}' | grep -E '^(\.git/|\.venv/|venv/|\.ci-venv/|\.pytest_cache/|\.ruff_cache/|\.mypy_cache/|\.opencontext/|\.storage/|\.claude/|\.sdd/)' >/dev/null; then
    echo "ERROR: dev state leaked into release zip" >&2
    exit 1
fi
echo "clean: no dev-state directories inside"
