$ErrorActionPreference = 'Stop'
$kitDirectory = $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and start it.'
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and wait for the engine, then try again.' }
$expectedNames = @('Dockerfile', 'requirements.txt', 'INSTALL.sh', 'INSTALL.ps1', 'INSTALL.bat', 'README.txt')
$seenNames = @()
foreach ($line in Get-Content -LiteralPath (Join-Path $kitDirectory 'SHA256SUMS')) {
    if ($line -notmatch '^([a-f0-9]{64})  ([A-Za-z0-9.]+)$') { throw 'Invalid checksum manifest. Download a fresh kit.' }
    $expectedHash = $Matches[1]
    $fileName = $Matches[2]
    if ($fileName -notin $expectedNames -or $fileName -in $seenNames) { throw 'Unexpected checksum entry.' }
    $seenNames += $fileName
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash([System.IO.File]::ReadAllBytes((Join-Path $kitDirectory $fileName)))
        $fileHash = [System.BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()
    } finally { $hasher.Dispose() }
    if ($fileHash -ne $expectedHash) { throw "Kit integrity check failed: $fileName. Download and extract a fresh kit." }
}
if ($seenNames.Count -ne $expectedNames.Count) { throw 'Incomplete checksum manifest.' }
Write-Host 'This builds symphony-sandbox:stage3 (runtime 6.0) using Docker.'
Write-Host 'First build downloads several GB from Docker Hub, Debian and PyPI. Keep at least 12 GB free.'
Write-Host 'No chat, model, volume or cache is deleted. An existing runtime tag will be updated.'
$answer = Read-Host 'Build the runtime now? [y/N]'
if ($answer -notin @('y', 'yes')) { Write-Host 'Cancelled. Nothing changed.'; exit 0 }
docker build --tag symphony-sandbox:stage3 --file (Join-Path $kitDirectory 'Dockerfile') $kitDirectory
if ($LASTEXITCODE -ne 0) { throw 'Runtime build failed. See Docker output above; you can run this installer again.' }
$imageJson = docker image inspect symphony-sandbox:stage3
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the built image.' }
$imageInfo = $imageJson | ConvertFrom-Json
if ($imageInfo[0].Config.Labels.'com.symphony.runtime.version' -ne '6.0') { throw 'Unexpected runtime version after build.' }
Write-Host 'Runtime ready. Reopen Settings > General in Symphony to refresh diagnostics.'
