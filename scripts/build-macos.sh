#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
bash "$ROOT/scripts/check-stage7-macos.sh"

if [[ ! -f "$ROOT/src-tauri/tauri.release.conf.json" ]]; then
  echo "Missing src-tauri/tauri.release.conf.json." >&2
  echo "Copy tauri.release.conf.example.json and set a real HTTPS endpoint and public updater key." >&2
  exit 2
fi
if grep -q 'REPLACE_WITH' "$ROOT/src-tauri/tauri.release.conf.json"; then
  echo "Release config still contains placeholders." >&2
  exit 2
fi
for variable in TAURI_SIGNING_PRIVATE_KEY APPLE_SIGNING_IDENTITY; do
  if [[ -z "${!variable:-}" ]]; then
    echo "Missing release secret: $variable" >&2
    exit 2
  fi
done
if [[ -z "${APPLE_API_KEY:-}" || -z "${APPLE_API_ISSUER:-}" || -z "${APPLE_API_KEY_PATH:-}" ]]; then
  if [[ -z "${APPLE_ID:-}" || -z "${APPLE_PASSWORD:-}" || -z "${APPLE_TEAM_ID:-}" ]]; then
    echo "Set notarization credentials: APPLE_API_KEY/APPLE_API_ISSUER/APPLE_API_KEY_PATH or APPLE_ID/APPLE_PASSWORD/APPLE_TEAM_ID." >&2
    exit 2
  fi
fi

npm --prefix frontend ci
npm --prefix frontend exec -- tauri icon "$ROOT/assets/app-icon.svg" --output "$ROOT/src-tauri/icons"
npm --prefix frontend test
npm --prefix frontend run build

bash "$ROOT/scripts/build-sidecar.sh"
.venv-desktop/bin/python -m pytest -q
cargo test --manifest-path src-tauri/Cargo.toml
npm --prefix frontend exec -- tauri build --config "$ROOT/src-tauri/tauri.release.conf.json"

echo "Signed app/DMG and updater artifacts are under src-tauri/target/release/bundle/."
