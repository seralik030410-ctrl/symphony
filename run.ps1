$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$frontendPath = Join-Path $projectRoot "frontend"
$indexPath = Join-Path $frontendPath "dist\index.html"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

if (-not (Test-Path -LiteralPath $indexPath)) {
    Push-Location $frontendPath
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

Push-Location $projectRoot
try {
    Write-Host "Symphony 2.0: http://127.0.0.1:8765"
    & $pythonPath -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
} finally {
    Pop-Location
}

