# Plain equivalent of the justfile: scripts/dev.ps1 {test|smoke|lint|serve} [args...]
param(
    [Parameter(Position = 0)][string]$Command = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @()
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $Root 'backend')
try {
    switch ($Command) {
        'test'  { uv run pytest @Rest }
        'smoke' { uv run pytest -m smoke @Rest }
        'lint'  {
            uv run ruff check .
            if ($LASTEXITCODE -eq 0) { uv run ruff format --check . }
            if ($LASTEXITCODE -eq 0) { uv run mypy }
        }
        'serve' { uv run videoflow serve @Rest }
        default { Write-Error 'usage: scripts/dev.ps1 {test|smoke|lint|serve} [args...]'; exit 2 }
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
