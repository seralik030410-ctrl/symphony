$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ''
Write-Host 'Symphony 2.0 - first setup' -ForegroundColor Cyan
Write-Host 'This keeps all chats on this computer and binds only to 127.0.0.1.'

$missing = @()
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $missing += 'Python 3.12+ — https://www.python.org/downloads/windows/' }
else {
    & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
    if ($LASTEXITCODE -ne 0) { $missing += 'Python 3.12+ — https://www.python.org/downloads/windows/' }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { $missing += 'Docker Desktop — https://www.docker.com/products/docker-desktop/' }
if (-not (Get-Command ollama -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'))) {
    $missing += 'Ollama — https://ollama.com/download/windows'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html')) -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    $missing += 'Node.js 20+ — https://nodejs.org/ (only because this package has no prebuilt frontend)'
}
if ($missing.Count) {
    Write-Host 'Install these prerequisites, start Docker Desktop once, then run this file again:' -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host " - $_" }
    exit 2
}

$driveName = [System.IO.Path]::GetPathRoot($projectRoot).TrimEnd(':\')
$free = (Get-PSDrive -Name $driveName).Free
if ($free -lt 18GB) {
    Write-Warning ('Only {0:N1} GB is free. First setup may need about 18 GB for qwen3.5:9b, Docker layers and Python packages.' -f ($free / 1GB))
}
Write-Host ''
Write-Host 'The next step will:'
Write-Host ' - create a private Python environment inside this folder;'
Write-Host ' - download Python packages;'
Write-Host ' - start Docker Desktop/Ollama if needed;'
Write-Host ' - build the isolated runtime image;'
Write-Host ' - download qwen3.5:9b (about 6.6 GB) if it is missing;'
Write-Host ' - open Symphony at http://127.0.0.1:8765.'
Write-Host 'It does not upload chats and does not delete Docker data, models or cache.'
$answer = Read-Host 'Continue? [y/N]'
if ($answer -notin @('y', 'Y', 'yes', 'YES')) { Write-Host 'Cancelled. Nothing changed.'; exit 0 }

$env:SYMPHONY_PULL_MISSING_MODEL = '1'
$env:SYMPHONY_OLLAMA_MODEL = 'qwen3.5:9b'
& (Join-Path $PSScriptRoot 'start-all.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
