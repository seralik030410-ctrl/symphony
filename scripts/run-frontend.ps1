$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $projectRoot "frontend")
try {
    npm run dev
} finally {
    Pop-Location
}

