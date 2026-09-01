$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$imageName = if ($env:SYMPHONY_SANDBOX_IMAGE) { $env:SYMPHONY_SANDBOX_IMAGE } else { "symphony-sandbox:stage3" }
$runtimePath = Join-Path $projectRoot "runtime-image"

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker info *> $null
$dockerReady = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousPreference
if (-not $dockerReady) {
    throw "Docker Desktop is not running. Start it, then run this command again."
}

docker build --tag $imageName $runtimePath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Sandbox runtime is ready: $imageName"
