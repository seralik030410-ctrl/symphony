$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Push-Location $projectRoot
try {
    & $pythonPath -m pytest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Push-Location "frontend"
    try {
        npm test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}

