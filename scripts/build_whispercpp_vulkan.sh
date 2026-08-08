#!/usr/bin/env bash
# 配布版に同梱する whisper.cpp(Vulkan)をビルドする。
#
# Vulkanを選ぶ理由: ROCmを一切リンクせず、GPUドライバ付属のVulkanローダーだけで
# 動く。AMD/NVIDIA/Intelを1ビルドで賄えるので、GPUごとにビルドを分けずに済む。
# HIP版より13%遅いが、配布のしやすさが桁違いに違う(docs/verify_rocm.md)。
#
# 静的リンクで1ファイルにする(共有ライブラリを散らすと同梱と実行時解決が面倒)。
#
#   ./scripts/build_whispercpp_vulkan.sh
#   → frontend/src-tauri/resources/bin/whisper-cli
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${KS_WHISPERCPP_SRC:-$HOME/.cache/whisper-local/src/whisper.cpp}"
OUT="frontend/src-tauri/resources/bin/whisper-cli"

if ! command -v glslc > /dev/null; then
  echo "Vulkanのビルドツールがありません。次を実行してください:" >&2
  echo "  sudo apt install libvulkan-dev glslc glslang-tools spirv-headers" >&2
  exit 1
fi

if [ ! -d "$SRC" ]; then
  mkdir -p "$(dirname "$SRC")"
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$SRC"
fi

cmake -S "$SRC" -B "$SRC/build-vk-static" \
  -DGGML_VULKAN=ON -DBUILD_SHARED_LIBS=OFF \
  -DWHISPER_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$SRC/build-vk-static" -j "$(nproc)" --target whisper-cli

mkdir -p "$(dirname "$OUT")"
cp "$SRC/build-vk-static/bin/whisper-cli" "$OUT"
chmod +x "$OUT"
echo "=== できました: $OUT ($(du -h "$OUT" | cut -f1)) ==="
