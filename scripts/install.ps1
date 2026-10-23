<#
.SYNOPSIS
  Video-Flow installer for Windows 11 (x64 and ARM64).
.DESCRIPTION
  Installs uv (if missing), Python 3.13, the backend with the accelerator extra matching the
  detected hardware, FFmpeg >= 6.1 (static build in tools\ffmpeg) and checks Node 22 + pnpm
  (only needed to build the frontend).
.PARAMETER CpuOnly
  Skip hardware detection, install the CPU extra.
.PARAMETER Extra
  Extras to install (repeatable). Accelerator extras are mutually exclusive:
  cpu | openvino | cuda | directml | qnn. Others: whisper.
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
    [switch]$NoFfmpeg,
    [switch]$NoFrontendCheck
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$FfmpegMin = [version]'6.1'
$IsArm = ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') -or ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64')

# Pinned static builds (override with VIDEOFLOW_FFMPEG_URL / VIDEOFLOW_FFMPEG_SHA256).
if ($IsArm) {
    $DefaultUrl = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-winarm64-gpl-7.1.zip'
} else {
    $DefaultUrl = 'https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip'
}
$FfmpegUrl = if ($env:VIDEOFLOW_FFMPEG_URL) { $env:VIDEOFLOW_FFMPEG_URL } else { $DefaultUrl }
$FfmpegSha256 = $env:VIDEOFLOW_FFMPEG_SHA256

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
        Warn 'AMD Ryzen AI NPU detected: the VitisAI EP ships with the Ryzen AI SDK (not on PyPI). See docs\dependencies.md. Falling back to a GPU/CPU extra.'
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
    Log 'downloading static FFmpeg into tools\ffmpeg'
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("videoflow-ffmpeg-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'ffmpeg.zip'
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $zip -UseBasicParsing
        if ($FfmpegSha256) {
            $actual = (Get-FileHash $zip -Algorithm SHA256).Hash
            if ($actual -ne $FfmpegSha256.ToUpper()) { throw 'FFmpeg checksum mismatch' }
        } else {
            Warn 'VIDEOFLOW_FFMPEG_SHA256 not set: archive integrity not verified'
        }
        Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x') -Force
        $found = Get-ChildItem -Path (Join-Path $tmp 'x') -Recurse -Filter ffmpeg.exe | Select-Object -First 1
        if (-not $found) { throw 'ffmpeg.exe not found in archive' }
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Copy-Item $found.FullName $dir -Force
        Copy-Item (Join-Path $found.DirectoryName 'ffprobe.exe') $dir -Force
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

$syncArgs = @('sync')
foreach ($e in $Extra) { $syncArgs += @('--extra', $e) }
Push-Location (Join-Path $Root 'backend')
try {
    uv @syncArgs
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
} finally {
    Pop-Location
}
Log 'done. Run: scripts\run.ps1   (tests: scripts\dev.ps1 test)'
