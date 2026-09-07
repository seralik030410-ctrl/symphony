#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This launcher is for macOS. On Windows use START.bat." >&2
  exit 2
fi

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

load_local_env() {
  local file="$ROOT/.env" raw line name value first last
  [[ -f "$file" ]] || return 0
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="$(trim "$raw")"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    if [[ "$line" != *=* ]]; then
      echo "Invalid line in .env: expected NAME=value" >&2
      exit 2
    fi
    name="$(trim "${line%%=*}")"
    value="$(trim "${line#*=}")"
    if [[ ! "$name" =~ ^SYMPHONY_[A-Z0-9_]+$ ]]; then
      echo "Unsupported variable in .env: $name" >&2
      exit 2
    fi
    if (( ${#value} >= 2 )); then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ ( "$first" == '"' && "$last" == '"' ) || ( "$first" == "'" && "$last" == "'" ) ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi
    if [[ -z "${!name+x}" ]]; then
      printf -v "$name" '%s' "$value"
      export "$name"
    fi
  done < "$file"
}

http_ready() {
  curl --fail --silent --show-error --max-time 2 "$1" >/dev/null 2>&1
}

wait_until() {
  local url="$1" seconds="$2" label="$3" deadline
  deadline=$((SECONDS + seconds))
  while (( SECONDS < deadline )); do
    if http_ready "$url"; then return 0; fi
    printf '.'
    sleep 2
  done
  echo
  echo "$label did not become ready in ${seconds}s." >&2
  return 1
}

require_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.12+ is required. Install it from https://www.python.org/downloads/macos/" >&2
    exit 2
  fi
  python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ is required")
PY
}

load_local_env

APP_URL="http://127.0.0.1:${SYMPHONY_PORT:-8765}"
OLLAMA_URL="${SYMPHONY_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
DEFAULT_MODEL="${SYMPHONY_OLLAMA_MODEL:-qwen3.5:9b}"
SANDBOX_IMAGE="${SYMPHONY_SANDBOX_IMAGE:-symphony-sandbox:stage3}"
START_TIMEOUT="${SYMPHONY_START_TIMEOUT:-30}"
DOCKER_TIMEOUT="${SYMPHONY_DOCKER_TIMEOUT:-120}"
VENV_PYTHON="$ROOT/.venv/bin/python"
FRONTEND_INDEX="$ROOT/frontend/dist/index.html"
LOGS="$ROOT/data/logs"
mkdir -p "$LOGS"

echo
echo "FinCtrl for macOS"
echo "Starting local chat, Ollama and the optional Docker sandbox..."

if [[ ! -x "$VENV_PYTHON" ]]; then
  require_python
  echo "[1/4] Creating the Python environment..."
  python3 -m venv "$ROOT/.venv"
fi
if ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  echo "The existing .venv is not Python 3.12+. Remove .venv and run START.command again." >&2
  exit 2
fi

if ! "$VENV_PYTHON" -c "import fastapi, reportlab, openpyxl, docx, pptx, pymupdf, PIL" >/dev/null 2>&1; then
  echo "[1/4] Installing FinCtrl dependencies..."
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -e "$ROOT"
else
  echo "[1/4] Python dependencies are ready."
fi

if [[ ! -f "$FRONTEND_INDEX" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "The prebuilt frontend is missing. Install Node.js 20+ or download the complete release archive." >&2
    exit 2
  fi
  echo "[1/4] Building the frontend..."
  npm --prefix "$ROOT/frontend" install
  npm --prefix "$ROOT/frontend" run build
fi

docker_ready=false
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    docker_ready=true
  elif [[ -d "/Applications/Docker.app" ]]; then
    echo -n "[2/4] Starting Docker Desktop"
    open -g -a Docker
    deadline=$((SECONDS + DOCKER_TIMEOUT))
    while (( SECONDS < deadline )); do
      if docker info >/dev/null 2>&1; then docker_ready=true; break; fi
      printf '.'
      sleep 3
    done
    echo
  fi
fi

if [[ "$docker_ready" == true ]]; then
  runtime_version="$(docker image inspect --format '{{ index .Config.Labels "com.symphony.runtime.version" }}' "$SANDBOX_IMAGE" 2>/dev/null || true)"
  if [[ "$runtime_version" != "6.0" ]]; then
    echo "[2/4] Building the Docker sandbox. The first build can take several minutes..."
    docker build --tag "$SANDBOX_IMAGE" "$ROOT/runtime-image"
  else
    echo "[2/4] Docker sandbox is ready."
  fi
else
  echo "[2/4] Docker is unavailable. Ordinary chat will work; tools, documents and OCR stay disabled."
fi

OLLAMA_BIN="$(command -v ollama 2>/dev/null || true)"
if [[ -z "$OLLAMA_BIN" && -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
  OLLAMA_BIN="/Applications/Ollama.app/Contents/Resources/ollama"
fi

if http_ready "$OLLAMA_URL/api/tags"; then
  echo "[3/4] Ollama is already running."
else
  if [[ -z "$OLLAMA_BIN" ]]; then
    echo "Ollama is required for local chat. Install it from https://ollama.com/download/mac" >&2
    exit 2
  fi
  echo -n "[3/4] Starting Ollama"
  if [[ -d "/Applications/Ollama.app" ]]; then
    open -g -a Ollama
  else
    nohup "$OLLAMA_BIN" serve >"$LOGS/ollama.stdout.log" 2>"$LOGS/ollama.stderr.log" &
  fi
  wait_until "$OLLAMA_URL/api/tags" 45 "Ollama" || exit 2
  echo
fi

if [[ -z "$OLLAMA_BIN" ]]; then
  echo "[3/4] Ollama is running, but its CLI was not found; model availability will be shown in FinCtrl."
elif ! "$OLLAMA_BIN" show "$DEFAULT_MODEL" >/dev/null 2>&1; then
  pull_model=false
  if [[ "${SYMPHONY_PULL_MISSING_MODEL:-0}" == "1" ]]; then
    pull_model=true
  elif [[ -t 0 ]]; then
    read -r -p "Model $DEFAULT_MODEL is missing. Download it now (several GB)? [y/N] " answer
    [[ "$answer" =~ ^([yY]|[yY][eE][sS])$ ]] && pull_model=true
  fi
  if [[ "$pull_model" == true ]]; then
    "$OLLAMA_BIN" pull "$DEFAULT_MODEL"
  else
    echo "[3/4] Model $DEFAULT_MODEL is not installed. Run: ollama pull $DEFAULT_MODEL"
  fi
else
  echo "[3/4] Ollama model $DEFAULT_MODEL is ready."
fi

if http_ready "$APP_URL/api/health"; then
  echo "[4/4] FinCtrl is already running."
else
  echo -n "[4/4] Starting FinCtrl"
  nohup "$VENV_PYTHON" -m uvicorn backend.main:app \
    --host 127.0.0.1 --port "${SYMPHONY_PORT:-8765}" \
    >"$LOGS/symphony.stdout.log" 2>"$LOGS/symphony.stderr.log" &
  backend_pid=$!
  if ! wait_until "$APP_URL/api/health" "$START_TIMEOUT" "FinCtrl backend"; then
    if kill -0 "$backend_pid" >/dev/null 2>&1; then kill "$backend_pid" >/dev/null 2>&1 || true; fi
    echo "See $LOGS/symphony.stderr.log" >&2
    exit 2
  fi
  echo
fi

echo
echo "Ready: $APP_URL"
open "$APP_URL"
