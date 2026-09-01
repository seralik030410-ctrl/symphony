param([switch]$SkipFrontend)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"

if (-not (Test-Path -LiteralPath $venvPath)) {
    python -m venv $venvPath
}

$pythonPath = Join-Path $venvPath "Scripts\python.exe"
& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install -e "$projectRoot[dev]"

if (-not $SkipFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm is required only to rebuild missing frontend assets. Install Node.js 20+ or use the complete release ZIP."
    }
    Push-Location (Join-Path $projectRoot "frontend")
    try {
        npm install
    } finally {
        Pop-Location
    }
}

Write-Host "Symphony dependencies are ready."
