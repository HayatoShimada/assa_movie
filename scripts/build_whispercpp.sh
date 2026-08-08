#!/usr/bin/env bash
# 配布版に同梱する whisper.cpp をビルドする。バックエンドはOSで選ぶ。
#
#   Linux   → Vulkan。ROCmを一切リンクせず、GPUドライバ付属のVulkanローダーだけで
#             動く。AMD/NVIDIA/Intelを1ビルドで賄える。HIP版より13%遅いが、
#             配布のしやすさが桁違いに違う(docs/verify_rocm.md)
#   macOS   → Metal。Apple純正で追加の依存が要らない
#   Windows → Vulkan(SDKが要る)。無ければCPUビルドに落とす
#
# 静的リンクで1ファイルにする(共有ライブラリを散らすと同梱と実行時解決が面倒)。
#
#   ./scripts/build_whispercpp.sh
#   → frontend/src-tauri/resources/bin/whisper-cli
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${KS_WHISPERCPP_SRC:-$HOME/.cache/whisper-local/src/whisper.cpp}"
OUT="frontend/src-tauri/resources/bin/whisper-cli"

case "$(uname -s)" in
  Darwin)
    # Metalは追加の依存が要らない
    BACKEND_FLAGS="-DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON"
    BACKEND_NAME="Metal"
    ;;
  *)
    if command -v glslc > /dev/null; then
      BACKEND_FLAGS="-DGGML_VULKAN=ON"
      BACKEND_NAME="Vulkan"
    else
      # SDKが無い環境ではCPUで作る(遅いが動かないよりよい)
      echo "⚠ Vulkanのビルドツールが無いのでCPUビルドにします。" >&2
      echo "  Linuxなら: sudo apt install libvulkan-dev glslc glslang-tools spirv-headers" >&2
      BACKEND_FLAGS=""
      BACKEND_NAME="CPU"
    fi
    ;;
esac
echo "=== whisper.cpp を $BACKEND_NAME でビルドします ==="

if [ ! -d "$SRC" ]; then
  mkdir -p "$(dirname "$SRC")"
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$SRC"
fi

BUILD_DIR="$SRC/build-bundled"
# shellcheck disable=SC2086  # フラグは意図的に分割する
cmake -S "$SRC" -B "$BUILD_DIR" $BACKEND_FLAGS \
  -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release
# nprocはmacOSに無い
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
cmake --build "$BUILD_DIR" -j "$JOBS" --config Release --target whisper-cli

mkdir -p "$(dirname "$OUT")"
# Windowsは Release/whisper-cli.exe に出る
cp "$BUILD_DIR/bin/whisper-cli" "$OUT" 2>/dev/null \
  || cp "$BUILD_DIR/bin/Release/whisper-cli.exe" "$OUT.exe"
chmod +x "$OUT"
echo "=== できました: $OUT ($(du -h "$OUT" | cut -f1)) ==="
