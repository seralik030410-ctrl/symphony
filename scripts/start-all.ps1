$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "load-local-env.ps1")
$dataPath = Join-Path $projectRoot "data"
$logsPath = Join-Path $dataPath "logs"
$frontendPath = Join-Path $projectRoot "frontend"
$frontendIndex = Join-Path $frontendPath "dist\index.html"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$sandboxImage = if ($env:SYMPHONY_SANDBOX_IMAGE) { $env:SYMPHONY_SANDBOX_IMAGE } else { "symphony-sandbox:stage3" }

New-Item -ItemType Directory -Force -Path $logsPath | Out-Null

function Test-HttpEndpoint([string]$Url) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Invoke-DockerProbe([string]$Arguments) {
    # A crashed Desktop can leave its named pipe alive indefinitely. Bound each
    # probe as well as the outer readiness loop, so basic chat can still start.
    $probe = New-Object System.Diagnostics.Process
    $probe.StartInfo.FileName = (Get-Command docker).Source
    $probe.StartInfo.Arguments = $Arguments
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    try {
        [void]$probe.Start()
        $stdout = $probe.StandardOutput.ReadToEndAsync()
        $stderr = $probe.StandardError.ReadToEndAsync()
        if (-not $probe.WaitForExit(5000)) {
            $probe.Kill()
            [void]$probe.WaitForExit(1000)
            return @{ Ready = $false; Output = "" }
        }
        return @{ Ready = $probe.ExitCode -eq 0; Output = $stdout.GetAwaiter().GetResult() }
    } catch { return @{ Ready = $false; Output = "" } }
    finally { $probe.Dispose() }
}

function Test-DockerReady {
    return (Invoke-DockerProbe "info").Ready
}

function Test-DockerImage([string]$Image) {
    if ($Image -notmatch '^[a-zA-Z0-9][a-zA-Z0-9._/:-]*$') { throw "Invalid sandbox image tag" }
    $result = Invoke-DockerProbe "image inspect $Image"
    if (-not $result.Ready) { return $false }
    try {
        $imageMetadata = $result.Output | ConvertFrom-Json
        return $imageMetadata[0].Config.Labels.'com.symphony.runtime.version' -eq "6.0"
    } catch { return $false }
}

function Wait-Until([scriptblock]$Check, [int]$Seconds, [string]$Label) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Check) { return $true }
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 2
    }
    Write-Host ""
    Write-Warning "$Label did not become ready in $Seconds seconds."
    return $false
}

Write-Host ""
Write-Host "Symphony 2.0" -ForegroundColor Cyan
Write-Host "Starting Ollama, Docker sandbox, frontend, and backend..."

$frontendBuilt = Test-Path -LiteralPath $frontendIndex
$pythonDependenciesReady = $false
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c "import fastapi, reportlab, openpyxl, docx, pptx, pymupdf, PIL" 2>$null
    $pythonDependenciesReady = $LASTEXITCODE -eq 0
}
if (-not $pythonDependenciesReady) {
    Write-Host "[1/4] Installing missing project dependencies..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "bootstrap.ps1") -SkipFrontend:$frontendBuilt
} elseif (-not $frontendBuilt -and -not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules"))) {
    Write-Host "[1/4] Installing frontend build dependencies..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "bootstrap.ps1")
} else {
    Write-Host "[1/4] Project dependencies are ready." -ForegroundColor Green
}

$dockerReady = $false
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $dockerReady = Test-DockerReady
    if (-not $dockerReady) {
        $dockerDesktopCandidates = @(
            (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
            (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
        )
        $dockerDesktop = $dockerDesktopCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if ($dockerDesktop) {
            Write-Host "[2/4] Starting Docker Desktop" -NoNewline
            Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
            $dockerReady = Wait-Until { Test-DockerReady } 120 "Docker Desktop"
        }
    }
}

if ($dockerReady) {
    if (-not (Test-DockerImage $sandboxImage)) {
        Write-Host "[2/4] Building the sandbox image $sandboxImage..." -ForegroundColor Yellow
        & (Join-Path $PSScriptRoot "build-runtime.ps1")
    } else {
        Write-Host "[2/4] Docker sandbox is ready." -ForegroundColor Green
    }
} else {
    Write-Warning "Docker is unavailable. Chat will start, but sandbox commands will remain disabled."
}

if (Test-HttpEndpoint "http://127.0.0.1:11434/api/tags") {
    Write-Host "[3/4] Ollama is already running." -ForegroundColor Green
} else {
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaCommand) {
        $ollamaCandidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
        if (Test-Path -LiteralPath $ollamaCandidate) {
            $ollamaExecutable = $ollamaCandidate
        } else {
            throw "Ollama is not installed. Install it from https://ollama.com/download/windows"
        }
    } else {
        $ollamaExecutable = $ollamaCommand.Source
    }
    Write-Host "[3/4] Starting Ollama" -NoNewline
    Start-Process -FilePath $ollamaExecutable -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    if (-not (Wait-Until { Test-HttpEndpoint "http://127.0.0.1:11434/api/tags" } 40 "Ollama")) {
        throw "Ollama did not start."
    }
    Write-Host "[3/4] Ollama is ready." -ForegroundColor Green
}

$ollamaExecutable = if ($ollamaExecutable) { $ollamaExecutable } elseif (Get-Command ollama -ErrorAction SilentlyContinue) { (Get-Command ollama).Source } else { Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
$defaultModel = if ($env:SYMPHONY_OLLAMA_MODEL) { $env:SYMPHONY_OLLAMA_MODEL } else { "qwen3.5:9b" }
& $ollamaExecutable show $defaultModel *> $null
if ($LASTEXITCODE -ne 0) {
    if ($env:SYMPHONY_PULL_MISSING_MODEL -eq "1") {
        Write-Host "[3/4] Downloading Ollama model $defaultModel. This is several GB and may take a while..." -ForegroundColor Yellow
        & $ollamaExecutable pull $defaultModel
        if ($LASTEXITCODE -ne 0) { throw "Ollama could not download $defaultModel. Run: ollama pull $defaultModel" }
    } else {
        Write-Warning "Ollama model $defaultModel is not installed. Run: ollama pull $defaultModel"
    }
} else {
    Write-Host "[3/4] Ollama model $defaultModel is ready." -ForegroundColor Green
}

$needsFrontendBuild = -not (Test-Path -LiteralPath $frontendIndex)
if (-not $needsFrontendBuild) {
    $latestSource = Get-ChildItem -LiteralPath (Join-Path $frontendPath "src") -Recurse -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    $needsFrontendBuild = $latestSource.LastWriteTimeUtc -gt (Get-Item -LiteralPath $frontendIndex).LastWriteTimeUtc
}
if ($needsFrontendBuild) {
    Write-Host "[4/4] Building frontend..." -ForegroundColor Yellow
    Push-Location $frontendPath
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

if (Test-HttpEndpoint "http://127.0.0.1:8765/api/health") {
    Write-Host "[4/4] Symphony is already running." -ForegroundColor Green
} else {
    $pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { (Get-Command python).Source }
    $stdoutLog = Join-Path $logsPath "symphony.stdout.log"
    $stderrLog = Join-Path $logsPath "symphony.stderr.log"
    $backend = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8765" `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -WindowStyle Hidden `
        -PassThru
    if (-not (Wait-Until { Test-HttpEndpoint "http://127.0.0.1:8765/api/health" } 30 "Symphony backend")) {
        throw "Symphony backend failed to start. Check $stderrLog"
    }
    Write-Host "[4/4] Symphony backend is ready (PID $($backend.Id))." -ForegroundColor Green
}

Write-Host ""
Write-Host "Ready: http://127.0.0.1:8765" -ForegroundColor Cyan
Start-Process "http://127.0.0.1:8765" | Out-Null
