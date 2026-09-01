$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $projectRoot 'release'
$output = Join-Path $releaseRoot 'Symphony-2.0-Windows.zip'
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Build frontend first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.git'))) { throw 'A local Git repository is required.' }
$dirty = git -C $projectRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Git repository.' }
if ($dirty) { throw 'Commit the release contents before packaging so the ZIP is reproducible.' }
New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
if (Test-Path -LiteralPath $output) {
    $resolvedRelease = [System.IO.Path]::GetFullPath($releaseRoot)
    $resolvedOutput = [System.IO.Path]::GetFullPath($output)
    if (-not $resolvedOutput.StartsWith($resolvedRelease + [System.IO.Path]::DirectorySeparatorChar)) { throw 'Unsafe release output path.' }
    Remove-Item -LiteralPath $resolvedOutput
}
git -C $projectRoot archive --format=zip --output=$output --prefix=Symphony-2.0/ HEAD
if ($LASTEXITCODE -ne 0) { throw 'git archive failed.' }
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash
Set-Content -LiteralPath ($output + '.sha256.txt') -Value "$hash  Symphony-2.0-Windows.zip" -Encoding ascii
Write-Host "Created: $output"
Write-Host "SHA-256: $hash"
