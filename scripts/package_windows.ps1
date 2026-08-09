#!/usr/bin/env pwsh
<#
.SYNOPSIS
Windows版のインストーラを手元で作る。

.DESCRIPTION
これまで手順は .github/workflows/release.yml の中にしか無く、
手元で作るには YAML を読んで真似するしかなかった(`./dev.sh package` は
Linux/macOS 向けで、whisper.cpp も ffmpeg も Windows の作り方と違う)。

やること:
  1. Pythonサイドカー(PyInstaller。torchは入れない)
  2. whisper.cpp(Vulkan)
  3. ffmpeg(MSYS2が要る。無ければ案内して止まる)
  4. 話者分離モデル(ONNX 76MB)
  5. Tauriでパッケージ

.PARAMETER SkipFfmpeg
ffmpegの再ビルドを飛ばす。既に resources/bin にあるときだけ使う。

.PARAMETER SkipWhisperCpp
whisper.cppの再ビルドを飛ばす。既に resources/bin にあるときだけ使う。

.EXAMPLE
./scripts/package_windows.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFfmpeg,
    [switch]$SkipWhisperCpp
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Resources = Join-Path $RepoRoot "frontend\src-tauri\resources"

function Require-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "$name が見つかりません。$hint"
    }
}

Require-Command bash "Git for Windows を入れてください(サイドカーのビルドに使います)"
Require-Command uv "https://docs.astral.sh/uv/ を見て入れてください"
Require-Command npm "Node.js 20以降を入れてください"
Require-Command cargo "rustup を入れてください"

Write-Host "=== 1/5 Pythonサイドカー ===" -ForegroundColor Cyan
bash ./scripts/build_sidecar.sh
if ($LASTEXITCODE -ne 0) { throw "サイドカーのビルドに失敗しました" }

Write-Host "=== 2/5 whisper.cpp (Vulkan) ===" -ForegroundColor Cyan
if ($SkipWhisperCpp -and (Test-Path "$Resources\bin\whisper-cli.exe")) {
    Write-Host "  既にあるので飛ばします"
} else {
    # MAX_PATHを避けるため作業場所を短くする(vulkan-shaders-genが入れ子の
    # ExternalProjectを作り、MSBuildの中間ファイルが260文字を超える)
    ./scripts/build_whispercpp.ps1 -WorkDir C:\kw
}

Write-Host "=== 3/5 ffmpeg ===" -ForegroundColor Cyan
if ($SkipFfmpeg -and (Test-Path "$Resources\bin\ffmpeg.exe")) {
    Write-Host "  既にあるので飛ばします"
} elseif (Test-Path "$Resources\bin\ffmpeg.exe") {
    Write-Host "  既にあるので飛ばします(作り直すなら resources\bin\ffmpeg.exe を消してください)"
} else {
    # MSYS2のmingw64シェルでしか作れない。ここから起動する
    $msys = @("C:\msys64\usr\bin\bash.exe", "$env:RUNNER_TEMP\msys64\usr\bin\bash.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $msys) {
        throw @"
MSYS2 が見つかりません。ffmpegはMSYS2のmingw64環境でビルドします。

  1. https://www.msys2.org/ から入れる
  2. MSYS2 の MINGW64 シェルで次を実行:
       pacman -S --needed make diffutils mingw-w64-x86_64-gcc mingw-w64-x86_64-pkgconf ``
                          mingw-w64-x86_64-nasm mingw-w64-x86_64-libass ``
                          mingw-w64-x86_64-openh264 mingw-w64-x86_64-ffnvcodec-headers
  3. もう一度これを実行する

既に resources\bin\ffmpeg.exe があるなら -SkipFfmpeg で飛ばせます。
"@
    }
    $env:MSYSTEM = "MINGW64"
    & $msys -lc "cd '$($RepoRoot -replace '\\', '/')' && ./scripts/build_ffmpeg.sh"
    if ($LASTEXITCODE -ne 0) { throw "ffmpegのビルドに失敗しました" }
}

Write-Host "=== 4/5 話者分離モデル ===" -ForegroundColor Cyan
uv run --no-project python scripts/fetch_diarization_models.py
if ($LASTEXITCODE -ne 0) { throw "モデルの取得に失敗しました" }

Write-Host "=== 5/5 Tauriでパッケージ ===" -ForegroundColor Cyan
Push-Location frontend
try {
    npm run app:build
    if ($LASTEXITCODE -ne 0) { throw "tauri build に失敗しました" }
} finally {
    Pop-Location
}

$installer = Get-ChildItem "frontend\src-tauri\target\release\bundle\nsis\*-setup.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1
Write-Host "=== できました ===" -ForegroundColor Green
if ($installer) {
    Write-Host "  $($installer.FullName) ($([math]::Round($installer.Length / 1MB, 1))MB)"
    Write-Host "  検証: ./scripts/verify_windows.ps1 -Installer '$($installer.FullName)'"
}
