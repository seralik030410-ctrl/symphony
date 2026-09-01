#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Stage 7 desktop acceptance must run on macOS (current: $(uname -s))." >&2
  exit 2
fi

missing=0
for command in python3 node npm rustc cargo; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing dependency: $command" >&2
    missing=1
  fi
done
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Missing dependency: Xcode Command Line Tools (run: xcode-select --install)" >&2
  missing=1
fi
if [[ "$missing" -ne 0 ]]; then
  exit 2
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ is required")
PY

echo "macOS prerequisites are present."
echo "Architecture: $(uname -m); Rust host: $(rustc -vV | awk '/^host:/ {print $2}')"

