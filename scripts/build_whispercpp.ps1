# Windows向けの whisper.cpp(Vulkan) をビルドして同梱先に置く。
#
#   ./scripts/build_whispercpp.ps1
#   → frontend/src-tauri/resources/bin/whisper-cli.exe
#
# Linux/macOS は scripts/build_whispercpp.sh(Vulkan / Metal)。Windowsだけ別に
# しているのはMSVCが要るのと、下に書いた3つのWindows固有の罠があるため。
#
# なぜVulkanか: AMDのWindowsドライバはVulkanローダー(vulkan-1.dll)を標準で入れる。
# ROCmはWindows非対応、CTranslate2(faster-whisper)はCUDA専用なので、
# AMD機のWindowsで文字起こしをGPUに載せる方法は実質これだけになる。
# NVIDIA/Intelでも同じバイナリが動く。実行時に配るDLLは無い(ドライバ提供)。
[CmdletBinding()]
param(
    # MAX_PATH(260文字)を避けるための短い作業場所。理由は下記
    [string]$WorkDir = "C:\kw",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $RepoRoot "frontend\src-tauri\resources\bin"
$Out = Join-Path $Dest "whisper-cli.exe"
$LicenseDest = Join-Path $RepoRoot "frontend\src-tauri\resources\licenses\whispercpp"

if (-not $Force -and (Test-Path $Out)) {
    Write-Host "=== 既に置いてあります: $Out ==="
    exit 0
}

# ---- cmake ----
# VS付属のcmake(3.31系)は whisper.cpp の configure 中に 0xC0000409 で
# クラッシュする(実測)。単体版を優先する
$cmake = @(
    "C:\Program Files\CMake\bin\cmake.exe",
    "$env:ProgramFiles\CMake\bin\cmake.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $cmake) { $cmake = (Get-Command cmake -ErrorAction SilentlyContinue).Source }
if (-not $cmake) {
    throw "cmakeが見つかりません。`winget install Kitware.CMake` で入れてください"
}
Write-Host "cmake: $cmake ($(& $cmake --version | Select-Object -First 1))"

# ---- Vulkan SDK ----
# シェーダのコンパイル(glslc)とヘッダ・インポートライブラリに要る。
# 実行時には不要(vulkan-1.dllはGPUドライバが入れる)
if (-not $env:VULKAN_SDK) {
    # 既定の C:\VulkanSDK\<version>\ と、--root で入れた場所の両方を見る
    $candidates = @("$env:LOCALAPPDATA\ks-build\VulkanSDK") + @(
        Get-ChildItem "C:\VulkanSDK" -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | ForEach-Object { $_.FullName }
    )
    $env:VULKAN_SDK = $candidates |
        Where-Object { Test-Path (Join-Path $_ "Bin\glslc.exe") } | Select-Object -First 1
}
if (-not $env:VULKAN_SDK -or -not (Test-Path "$env:VULKAN_SDK\Bin\glslc.exe")) {
    throw "Vulkan SDKが見つかりません。https://vulkan.lunarg.com/sdk/home から導入してください"
}
$env:PATH = "$env:VULKAN_SDK\Bin;$env:PATH"
Write-Host "Vulkan SDK: $env:VULKAN_SDK"

# ---- ソース ----
# 作業場所を短くするのが要点。whisper.cpp の Vulkan バックエンドは
# vulkan-shaders-gen を入れ子のExternalProjectとしてビルドし、MSBuildの
# 中間ファイル(.tlog)のパスが260文字を超えて DirectoryNotFoundException になる。
# リポジトリ直下でビルドすると必ず踏む
$src = Join-Path $WorkDir "whisper.cpp"
$build = Join-Path $WorkDir "b"
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
if (-not (Test-Path "$src\CMakeLists.txt")) {
    Write-Host "=== ソースを取得 ==="
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp $src
}

Write-Host "=== configure (Vulkan) ==="
& $cmake -S $src -B $build -DGGML_VULKAN=ON -DBUILD_SHARED_LIBS=OFF `
    -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "configureに失敗しました" }

Write-Host "=== ビルド ==="
& $cmake --build $build --config Release --target whisper-cli
if ($LASTEXITCODE -ne 0) { throw "ビルドに失敗しました" }

$built = Get-ChildItem "$build\bin" -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
if (-not $built) { throw "whisper-cli.exe が見つかりません" }

New-Item -ItemType Directory -Path $Dest, $LicenseDest -Force | Out-Null
Copy-Item $built.FullName $Out -Force
# MITなので著作権表示とライセンス文を添えれば足りる
Copy-Item "$src\LICENSE" (Join-Path $LicenseDest "LICENSE.txt") -Force
$commit = (git -C $src rev-parse HEAD)
Set-Content -Path (Join-Path $LicenseDest "VERSION.txt") -Encoding utf8 -Value @"
whisper.cpp (https://github.com/ggml-org/whisper.cpp)
commit: $commit
build:  GGML_VULKAN=ON / static / Release
"@

Write-Host "=== できました ==="
Get-Item $Out | Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table -AutoSize
Write-Host "ライセンス表記: $LicenseDest"
