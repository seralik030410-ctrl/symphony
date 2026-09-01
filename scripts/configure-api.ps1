$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"

function Read-Default([string]$Prompt, [string]$Default) {
    $answer = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer.Trim()
}

function Convert-SecureValue([Security.SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Save-Profile([string]$Title, [string]$BaseUrl, [string]$Model, [string]$ApiKey) {
    if ($BaseUrl -notmatch '^https?://[^\s]+$') { throw "Base URL must start with http:// or https://" }
    if ($Title -match '[\r\n]' -or $Model -match '[\r\n]' -or $ApiKey -match '[\r\n]') {
        throw "Profile fields cannot contain a new line"
    }
    $updates = [ordered]@{
        SYMPHONY_OPENAI_PROFILE_NAME = $Title
        SYMPHONY_OPENAI_BASE_URL = $BaseUrl.TrimEnd('/')
        SYMPHONY_OPENAI_MODEL = $Model
        SYMPHONY_OPENAI_API_KEY = $ApiKey
    }
    $kept = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            $name = if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=') { $Matches[1] } else { "" }
            if (-not $updates.Contains($name)) { $kept.Add($line) }
        }
    }
    if ($kept.Count -and $kept[$kept.Count - 1]) { $kept.Add("") }
    $kept.Add("# Remote OpenAI-compatible profile. This file is local and ignored by Git.")
    foreach ($entry in $updates.GetEnumerator()) { $kept.Add("$($entry.Key)=$($entry.Value)") }
    [IO.File]::WriteAllLines($envPath, $kept, [Text.UTF8Encoding]::new($false))
}

Write-Host ""
Write-Host "Symphony 2.0 - remote API profile" -ForegroundColor Cyan
Write-Host "Ollama remains available. This adds one remote profile beside it."
Write-Host ""
Write-Host "  1. Z.AI / GLM"
Write-Host "  2. Qwen / DashScope International (Singapore)"
Write-Host "  3. Qwen / DashScope US (Virginia)"
Write-Host "  4. Other OpenAI-compatible API"
Write-Host "  5. Clear remote API profile"
$choice = Read-Host "Choose 1-5"

if ($choice -eq "5") {
    Save-Profile "OpenAI-compatible API" "http://127.0.0.1:1234/v1" "local-model" ""
    Write-Host "Remote cloud credentials cleared. Local Ollama is unchanged." -ForegroundColor Green
    Write-Host "Restart Symphony for the change to apply."
    exit 0
}

switch ($choice) {
    "1" {
        $title = "Z.AI / GLM"
        $baseUrl = "https://api.z.ai/api/paas/v4"
        $model = Read-Default "Model" "glm-5"
    }
    "2" {
        $title = "Qwen / DashScope International"
        $baseUrl = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        $model = Read-Default "Model" "qwen-plus"
    }
    "3" {
        $title = "Qwen / DashScope US"
        $baseUrl = "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
        $model = Read-Default "Model" "qwen-plus"
    }
    "4" {
        $title = Read-Default "Profile name" "OpenAI-compatible API"
        $baseUrl = Read-Default "Base URL ending before /chat/completions" "http://127.0.0.1:1234/v1"
        $model = Read-Default "Model" "local-model"
    }
    default { throw "Choose a number from 1 to 5" }
}

$secureKey = Read-Host "API key (input is hidden)" -AsSecureString
$apiKey = Convert-SecureValue $secureKey
if ([string]::IsNullOrWhiteSpace($apiKey)) { throw "API key cannot be empty" }
try {
    Save-Profile $title $baseUrl $model $apiKey
} finally {
    $apiKey = $null
}
Write-Host ""
Write-Host "Saved locally to .env. The key is ignored by Git and release packaging." -ForegroundColor Green
Write-Host "Restart Symphony, open Settings -> General, and choose $title / $model."
Write-Host "Only prompts sent through that selected profile leave the computer."
