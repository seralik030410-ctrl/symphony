#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

bash "$ROOT/scripts/start-macos.sh"
status=$?
if [[ "$status" -ne 0 ]]; then
  echo
    echo "FinCtrl could not start. Read the message above, then try again."
  if [[ -t 0 ]]; then
    read -r -p "Press Return to close this window..." _
  fi
  exit "$status"
fi
