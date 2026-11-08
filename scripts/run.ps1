# Start the native desktop app or pass any other CLI arguments through.
#   scripts/run.ps1                 -> videoflow desktop
#   scripts/run.ps1 --help          -> videoflow --help
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CliArgs = @())
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Ffmpeg = Join-Path $Root 'tools\ffmpeg'
if (Test-Path $Ffmpeg) { $env:PATH = "$Ffmpeg$([IO.Path]::PathSeparator)$env:PATH" }
Push-Location (Join-Path $Root 'backend')
try {
    if ($CliArgs.Count -eq 0) { $CliArgs = @('desktop') }
    # Existing environments show missing inference dependencies in component setup.
    $LocalCli = Join-Path $Root 'backend\.venv\Scripts\videoflow.exe'
    if (Test-Path $LocalCli) { & $LocalCli @CliArgs }
    else { uv run --inexact --extra desktop videoflow @CliArgs }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
