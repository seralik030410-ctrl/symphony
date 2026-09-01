#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -s)" == "Darwin" ]] || { echo "Build the macOS sidecar on macOS." >&2; exit 2; }
[[ -f frontend/dist/index.html ]] || { echo "Run npm --prefix frontend run build first." >&2; exit 2; }
python3 -m venv .venv-desktop
PYTHON="$ROOT/.venv-desktop/bin/python"
"$PYTHON" -m pip install --disable-pip-version-check -e '.[dev]' 'pyinstaller>=6.10,<7'
TARGET="$(rustc -vV | awk '/^host:/ {print $2}')"
mkdir -p "$ROOT/build/spec" "$ROOT/src-tauri/binaries"
"$PYTHON" -m PyInstaller \
  --noconfirm --clean --onefile \
  --name "symphony-backend-$TARGET" \
  --paths "$ROOT" \
  --collect-submodules backend \
  --copy-metadata symphony-2 --copy-metadata fastapi --copy-metadata uvicorn --copy-metadata httpx \
  --codesign-identity "${APPLE_SIGNING_IDENTITY:--}" \
  --add-data "$ROOT/backend/storage/migrations:backend/storage/migrations" \
  --add-data "$ROOT/backend/artifacts:backend/artifacts" \
  --add-data "$ROOT/backend/agent/extraction_worker.py:backend/agent" \
  --add-data "$ROOT/frontend/dist:frontend/dist" \
  --add-data "$ROOT/bundled-skills:bundled-skills" \
  --add-data "$ROOT/runtime-image:runtime-image" \
  --specpath "$ROOT/build/spec" \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/build/symphony-backend" \
  "$ROOT/desktop/sidecar.py"
cp "$ROOT/dist/symphony-backend-$TARGET" "$ROOT/src-tauri/binaries/symphony-backend-$TARGET"
chmod +x "$ROOT/src-tauri/binaries/symphony-backend-$TARGET"
# Exercise actual packaged startup/HTTP/readiness/parent shutdown, not a dummy binary.
SYMPHONY_TEST_SIDECAR="$ROOT/src-tauri/binaries/symphony-backend-$TARGET" \
  "$PYTHON" -m pytest tests/integration/test_desktop_sidecar.py -q
