$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "load-local-env.ps1")
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Push-Location $projectRoot
try {
    & $pythonPath -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
} finally {
    Pop-Location
}
