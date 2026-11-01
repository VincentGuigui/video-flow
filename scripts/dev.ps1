# Plain equivalent of the justfile: scripts/dev.ps1 {test|smoke|lint|serve|build|package} [args...]
param(
    [Parameter(Position = 0)][string]$Command = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @()
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

function Build-Frontend {
    Push-Location (Join-Path $Root 'frontend')
    try {
        if (-not (Test-Path 'node_modules')) { npm ci; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
        npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

if ($Command -eq 'build') { Build-Frontend; exit 0 }
if ($Command -eq 'package') {
    Build-Frontend
    Push-Location $Root
    try {
        # --inexact keeps the installed inference extras; desktop and PyInstaller are added.
        # package_release.py keeps models/, tools/, settings.json... beside the executable.
        uv run --project backend --inexact --extra desktop --group packaging `
            python scripts/package_release.py
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

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
        default { Write-Error 'usage: scripts/dev.ps1 {test|smoke|lint|serve|build|package} [args...]'; exit 2 }
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
