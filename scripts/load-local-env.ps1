# Loads a local .env without evaluating its contents. Existing process
# variables win, which keeps CI and explicit launch configuration predictable.
$localEnvPath = Join-Path $projectRoot ".env"
if (Test-Path -LiteralPath $localEnvPath) {
    foreach ($rawLine in Get-Content -LiteralPath $localEnvPath) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $separator = $line.IndexOf("=")
        if ($separator -lt 1) { throw "Invalid line in .env: expected NAME=value" }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($name -notmatch '^SYMPHONY_[A-Z0-9_]+$') {
            throw "Unsupported variable in .env: $name"
        }
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if (-not (Test-Path -LiteralPath "Env:$name")) {
            Set-Item -LiteralPath "Env:$name" -Value $value
        }
    }
}
