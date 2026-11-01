<#
.SYNOPSIS
  Video-Flow installer for Windows 11 (x64 and ARM64).
.DESCRIPTION
  Installs uv (if missing), Python 3.13, the backend with the accelerator extra matching the
  detected hardware, FFmpeg >= 6.1 (after your consent, a pinned and checksum-verified static
  build in tools\ffmpeg) and checks Node 22 + pnpm (only needed to build the frontend).
.PARAMETER CpuOnly
  Skip hardware detection, install the CPU extra.
.PARAMETER Extra
  Extras to install (repeatable). Accelerator extras are mutually exclusive:
  cpu | openvino | cuda | directml | qnn. Others: whisper.
.PARAMETER Yes
  Accept the FFmpeg download without asking.
.PARAMETER NoFfmpeg
  Do not check or install FFmpeg.
.PARAMETER NoFrontendCheck
  Do not check Node / pnpm.
.EXAMPLE
  scripts\install.ps1 -CpuOnly
#>
[CmdletBinding()]
param(
    [switch]$CpuOnly,
    [string[]]$Extra = @(),
    [switch]$Yes,
    [switch]$NoFfmpeg,
    [switch]$NoFrontendCheck
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$FfmpegMin = [version]'6.1'
$IsArm = ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') -or ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64')

# Pinned static build for x64, the same as backend\videoflow\media\ffmpeg_install.py (a test
# checks it). FFmpeg is a separate GPL-3.0 program built and distributed by gyan.dev; it is
# installed unchanged with its licence files. The full build is used because the sample
# generator needs flite. No build is pinned for ARM64: set both VIDEOFLOW_FFMPEG_URL and
# VIDEOFLOW_FFMPEG_SHA256 to use another archive (the checksum is always verified).
if ($IsArm) {
    $DefaultUrl = $null
    $DefaultSha256 = $null
} else {
    $DefaultUrl = 'https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-full_build.zip'
    $DefaultSha256 = 'd760e1b3574402ed18b4865851f87d87e73965a982e6453212df8621fed1c508'
}
if ($env:VIDEOFLOW_FFMPEG_URL) {
    $FfmpegUrl = $env:VIDEOFLOW_FFMPEG_URL
    $FfmpegSha256 = $env:VIDEOFLOW_FFMPEG_SHA256
    $FfmpegOrigin = 'the archive set in VIDEOFLOW_FFMPEG_URL'
} else {
    $FfmpegUrl = $DefaultUrl
    $FfmpegSha256 = $DefaultSha256
    $FfmpegOrigin = 'built and distributed by gyan.dev (https://www.gyan.dev/ffmpeg/builds/), about 178 MB'
}

function Log($m) { Write-Host "[install] $m" }
function Warn($m) { Write-Warning "[install] $m" }
function Have($n) { [bool](Get-Command $n -ErrorAction SilentlyContinue) }

function Install-Uv {
    if (Have 'uv') { Log "uv found: $(uv --version)"; return }
    Log 'installing uv'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    if (-not (Have 'uv')) { throw 'uv installed but not on PATH; open a new terminal and rerun' }
}

function Get-DevicePool {
    $names = @()
    try { $names += (Get-CimInstance Win32_PnPEntity -ErrorAction Stop | ForEach-Object { $_.Name }) } catch {}
    try { $names += (Get-CimInstance Win32_VideoController -ErrorAction Stop | ForEach-Object { $_.Name }) } catch {}
    return $names | Where-Object { $_ }
}

function Detect-Extra {
    $devices = Get-DevicePool
    $hit = { param($re) [bool]($devices | Where-Object { $_ -match $re }) }
    if ($IsArm -and (& $hit 'Hexagon|Snapdragon|Qualcomm.*NPU')) {
        Log 'detected Qualcomm NPU (Windows ARM64)'; return 'qnn'
    }
    if (& $hit 'Intel\(R\) AI Boost|Intel.*Neural Processing|Intel.*NPU') {
        Log 'detected Intel NPU'; return 'openvino'
    }
    if (& $hit 'Ryzen AI|AMD IPU|NPU Compute Accelerator') {
        Warn 'AMD Ryzen AI NPU detected: the VitisAI EP ships with the Ryzen AI SDK (not on PyPI). See docs\reference\dependencies.md. Falling back to a GPU/CPU extra.'
    }
    if ((Have 'nvidia-smi') -or (& $hit 'NVIDIA')) {
        if (-not $IsArm) { Log 'detected NVIDIA GPU'; return 'cuda' }
    }
    if (& $hit 'AMD|Radeon|Intel\(R\).*(Arc|Graphics|UHD|Iris)|Qualcomm.*Adreno') {
        Log 'detected a DirectX 12 GPU'; return 'directml'
    }
    return 'cpu'
}

function Get-FfmpegVersion([string]$exe) {
    try {
        $line = (& $exe -version 2>$null | Select-Object -First 1)
        if ($line -match 'ffmpeg version [nN]?(\d+)\.(\d+)') { return [version]"$($Matches[1]).$($Matches[2])" }
    } catch {}
    return $null
}

function Install-Ffmpeg {
    $dir = Join-Path $Root 'tools\ffmpeg'
    $local = Join-Path $dir 'ffmpeg.exe'
    if (Test-Path $local) {
        $v = Get-FfmpegVersion $local
        if ($v -and $v -ge $FfmpegMin) { Log "local FFmpeg $v in tools\ffmpeg"; return }
    }
    if ((Have 'ffmpeg') -and (Have 'ffprobe')) {
        $v = Get-FfmpegVersion (Get-Command ffmpeg).Source
        if ($v -and $v -ge $FfmpegMin) { Log "system FFmpeg $v is recent enough"; return }
        Warn "system FFmpeg '$v' is older than $FfmpegMin"
    }
    if (-not $FfmpegUrl -or -not $FfmpegSha256) {
        Warn "FFmpeg not installed: no pinned build for this machine. Install FFmpeg >= $FfmpegMin and put it on PATH or in tools\ffmpeg, or set VIDEOFLOW_FFMPEG_URL and VIDEOFLOW_FFMPEG_SHA256."
        return
    }
    Log "FFmpeg >= $FfmpegMin is needed. Video-Flow can download a static build into tools\ffmpeg:"
    Log "  source:  $FfmpegUrl"
    Log "  $FfmpegOrigin"
    Log '  licence: GPL-3.0; FFmpeg is a separate program, installed unchanged with its licence files'
    if (-not $Yes) {
        if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
            Warn "FFmpeg not installed: rerun with -Yes to accept the download, or install it later from the app"
            return
        }
        $answer = Read-Host '[install] Download and install FFmpeg? [y/N]'
        if ($answer -notmatch '^(y|yes)$') {
            Warn "FFmpeg not installed: install FFmpeg >= $FfmpegMin yourself, or later from the app"
            return
        }
    }
    Log 'downloading static FFmpeg into tools\ffmpeg'
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("videoflow-ffmpeg-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'ffmpeg.zip'
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $zip -UseBasicParsing
        $actual = (Get-FileHash $zip -Algorithm SHA256).Hash
        if ($actual -ne $FfmpegSha256.ToUpper()) {
            throw 'FFmpeg checksum mismatch (the distributor may have published a new build); nothing was installed'
        }
        Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x') -Force
        $found = Get-ChildItem -Path (Join-Path $tmp 'x') -Recurse -Filter ffmpeg.exe | Select-Object -First 1
        if (-not $found) { throw 'ffmpeg.exe not found in archive' }
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Copy-Item $found.FullName $dir -Force
        Copy-Item (Join-Path $found.DirectoryName 'ffprobe.exe') $dir -Force
        # The licence and readme files sit at the root of the archive folder, above bin\.
        foreach ($notice in 'LICENSE', 'README.txt') {
            $file = Get-ChildItem -Path (Join-Path $tmp 'x') -Recurse -Filter $notice | Select-Object -First 1
            if ($file) { Copy-Item $file.FullName $dir -Force }
        }
        Log "installed FFmpeg $(Get-FfmpegVersion $local) in tools\ffmpeg"
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Check-FrontendTools {
    if (Have 'node') {
        $major = [int](node -p 'process.versions.node.split(".")[0]')
        if ($major -ge 22) { Log "node $(node --version)" } else { Warn "Node $major found, 22+ needed to build the frontend" }
    } else {
        Warn 'Node 22+ not found (only needed to build the frontend): winget install OpenJS.NodeJS'
    }
    if (Have 'pnpm') { Log "pnpm $(pnpm --version)" }
    elseif (Have 'corepack') { Log "pnpm missing: enable with 'corepack enable pnpm'" }
    else { Warn 'pnpm not found (only needed to build the frontend): npm i -g pnpm' }
}

Install-Uv
Log 'ensuring Python 3.13'
uv python install 3.13
if ($LASTEXITCODE -ne 0) { throw 'uv python install failed' }

if (-not $NoFfmpeg) { Install-Ffmpeg }
if (-not $NoFrontendCheck) { Check-FrontendTools }

$accel = $Extra | Where-Object { $_ -in 'cpu', 'smoke', 'openvino', 'cuda', 'directml', 'qnn' } | Select-Object -First 1
if (-not $accel) {
    $accel = if ($CpuOnly) { 'cpu' } else { Detect-Extra }
    $Extra = @($Extra) + @($accel)
}
Log "accelerator extra: $accel"

$syncArgs = @('sync', '--extra', 'desktop')
foreach ($e in $Extra) { $syncArgs += @('--extra', $e) }
Push-Location (Join-Path $Root 'backend')
try {
    uv @syncArgs
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
} finally {
    Pop-Location
}
Log 'done. Run: scripts\run.ps1   (tests: scripts\dev.ps1 test)'
