#!/usr/bin/env bash
# 話者分離(ONNX)のモデルを取ってきて、配布物に同梱できる場所に置く。
# Windowsは scripts/fetch_diarization_models.ps1(中身は同じ)。
#
#   ./scripts/fetch_diarization_models.sh
#   → frontend/src-tauri/resources/models/...
#
# なぜ同梱するか: 配布物には torch を入れていない(11.5GBあるため)。torchを使う
# pyannoteはインストール版では動かず、ONNXが唯一使えるエンジンになる。モデルが
# 無いと設定タブで全エンジンが「未準備」になり、話者分離がまったく使えない。
#
# ライセンス: segmentation=MIT (c) 2022 CNRS / embedding=Apache-2.0 (3D-Speaker)
# 詳細は licenses/diarization-NOTICE.md
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

MODELS="$REPO_ROOT/frontend/src-tauri/resources/models"
LICENSE_DEST="$REPO_ROOT/frontend/src-tauri/resources/licenses/diarization"
CACHE="${KS_SRC_DIR:-$HOME/.cache/kirinuki-studio/src}/diarization"

SEG_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMB_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"

# backend/engines/diarize/onnx.py の SEGMENTATION_REL / EMBEDDING_REL と一致させる
SEG_OUT="$MODELS/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
EMB_OUT="$MODELS/speaker-embedding.onnx"

if [ -f "$SEG_OUT" ] && [ -f "$EMB_OUT" ]; then
  echo "=== 既に置いてあります: $MODELS ==="
  exit 0
fi

mkdir -p "$CACHE" "$LICENSE_DEST" "$(dirname "$SEG_OUT")"

echo "=== 分離モデルを取得 ==="
[ -f "$CACHE/segmentation.tar.bz2" ] || curl -fL --retry 3 -o "$CACHE/segmentation.tar.bz2" "$SEG_URL"
rm -rf "$CACHE/extract"
mkdir -p "$CACHE/extract"
tar -xf "$CACHE/segmentation.tar.bz2" -C "$CACHE/extract"
cp "$(find "$CACHE/extract" -name model.onnx | head -1)" "$SEG_OUT"
# 配布物に付属しているライセンス本文をそのまま持っていく
license="$(find "$CACHE/extract" -name LICENSE | head -1)"
if [ -n "$license" ]; then
  cp "$license" "$LICENSE_DEST/LICENSE-segmentation.txt"
else
  echo "⚠ segmentation の LICENSE が見つかりません" >&2
fi

echo "=== 埋め込みモデルを取得 (約68MB) ==="
[ -f "$CACHE/speaker-embedding.onnx" ] || curl -fL --retry 3 -o "$CACHE/speaker-embedding.onnx" "$EMB_URL"
cp "$CACHE/speaker-embedding.onnx" "$EMB_OUT"

cp "$REPO_ROOT/licenses/diarization-NOTICE.md" "$LICENSE_DEST/NOTICE.md"

echo "=== できました ==="
du -h "$SEG_OUT" "$EMB_OUT"
echo "ライセンス表記: $LICENSE_DEST"
