# Start the app (`videoflow serve`) or pass any other CLI arguments through.
#   scripts/run.ps1                 -> videoflow serve
#   scripts/run.ps1 --help          -> videoflow --help
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs = @())
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Ffmpeg = Join-Path $Root 'tools\ffmpeg'
if (Test-Path $Ffmpeg) { $env:PATH = "$Ffmpeg$([IO.Path]::PathSeparator)$env:PATH" }
Push-Location (Join-Path $Root 'backend')
try {
    if ($CliArgs.Count -eq 0) { $CliArgs = @('serve') }
    uv run videoflow @CliArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
