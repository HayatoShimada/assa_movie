# 話者分離(ONNX)のモデルを取ってきて、配布物に同梱できる場所に置く。
#
#   ./scripts/fetch_diarization_models.ps1
#   → frontend/src-tauri/resources/models/...
#
# なぜ同梱するか: 配布物には torch を入れていないため、pyannote は
# インストール版では動かない。ONNXが唯一使えるエンジンで、モデルが無いと
# 設定タブで全エンジンが「未準備」になり、話者分離がまったく使えない。
# 77MBなので同梱できる大きさ。
#
# ライセンス:
#   segmentation … MIT (c) 2022 CNRS。配布物にLICENSEが同梱されている
#   embedding    … 3D-Speaker (Apache-2.0)。sherpa-onnxが変換したもの
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Models = Join-Path $RepoRoot "frontend\src-tauri\resources\models"
$LicenseDest = Join-Path $RepoRoot "frontend\src-tauri\resources\licenses\diarization"
$Cache = Join-Path $env:LOCALAPPDATA "kirinuki-studio\src\diarization"

$SegUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
$EmbUrl = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"

# backend/engines/diarize/onnx.py の SEGMENTATION_REL / EMBEDDING_REL と一致させる
$SegOut = Join-Path $Models "sherpa-onnx-pyannote-segmentation-3-0\model.onnx"
$EmbOut = Join-Path $Models "speaker-embedding.onnx"

if (-not $Force -and (Test-Path $SegOut) -and (Test-Path $EmbOut)) {
    Write-Host "=== 既に置いてあります: $Models ==="
    exit 0
}

New-Item -ItemType Directory -Path $Cache, $Models, $LicenseDest -Force | Out-Null

Write-Host "=== 分離モデルを取得 ==="
$tar = Join-Path $Cache "segmentation.tar.bz2"
if ($Force -or -not (Test-Path $tar)) {
    Invoke-WebRequest $SegUrl -OutFile $tar -UseBasicParsing
}
$extract = Join-Path $Cache "extract"
if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
New-Item -ItemType Directory -Path $extract -Force | Out-Null
tar -xf $tar -C $extract
if ($LASTEXITCODE -ne 0) { throw "展開に失敗しました" }

$segSrc = Get-ChildItem $extract -Recurse -Filter "model.onnx" | Select-Object -First 1
if (-not $segSrc) { throw "model.onnx が見つかりません" }
New-Item -ItemType Directory -Path (Split-Path $SegOut) -Force | Out-Null
Copy-Item $segSrc.FullName $SegOut -Force

# 配布物に付属しているライセンス本文をそのまま持っていく
$segLicense = Get-ChildItem $extract -Recurse -Filter "LICENSE" | Select-Object -First 1
if ($segLicense) {
    Copy-Item $segLicense.FullName (Join-Path $LicenseDest "LICENSE-segmentation.txt") -Force
} else {
    Write-Warning "segmentation の LICENSE が見つかりません"
}

Write-Host "=== 埋め込みモデルを取得 (約68MB) ==="
$emb = Join-Path $Cache "speaker-embedding.onnx"
if ($Force -or -not (Test-Path $emb)) {
    Invoke-WebRequest $EmbUrl -OutFile $emb -UseBasicParsing
}
Copy-Item $emb $EmbOut -Force

Copy-Item (Join-Path $RepoRoot "licenses\diarization-NOTICE.md") (Join-Path $LicenseDest "NOTICE.md") -Force

Write-Host "=== できました ==="
Get-ChildItem $Models -Recurse -File |
    Select-Object @{n = 'Path'; e = { $_.FullName.Replace("$Models\", '') } },
                  @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } |
    Format-Table -AutoSize
Write-Host "ライセンス表記: $LicenseDest"
