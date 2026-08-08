#!/usr/bin/env bash
# 開発用のまとめて起動スクリプト。
#
#   ./dev.sh          バックエンド(8000)とフロント(5173)を同時起動
#   ./dev.sh api      バックエンドのみ
#   ./dev.sh web      フロントのみ
#   ./dev.sh sync     Python依存の同期(既定はROCm。WL_TORCH_EXTRA=cu128 でNVIDIA向け)
#   ./dev.sh whispercpp  whisper.cppをROCm向けにビルド(任意・ASRが約2.6倍速くなる)
#   ./dev.sh check    型・lint・テスト・ビルドを全部走らせる(コミット前用)
#   ./dev.sh e2e      E2Eテスト(FakeLLM・一時DBなのでGPU/LLM不要)
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-all}" in
  api)
    exec uv run uvicorn backend.app:app --reload --port 8000
    ;;
  web)
    cd frontend && exec npm run dev
    ;;
  e2e)
    cd frontend && exec npm run e2e "${@:2}"
    ;;
  whispercpp)
    # ROCmで最速のASR(公式Whisperの約2.6倍)。外部ビルドなので任意。
    # 用意されていればエンジン自動選択がこれを使い、無ければ公式版に落ちる。
    # 置き場所は WL_WHISPERCPP_HOME で変更できる(既定: ~/.cache/whisper-local)
    HOME_DIR="${WL_WHISPERCPP_HOME:-$HOME/.cache/whisper-local}"
    GPU_ARCH="${WL_GPU_ARCH:-gfx1100}"
    MODEL_NAME="${WL_GGML_MODEL:-ggml-large-v3.bin}"
    set -x
    mkdir -p "$HOME_DIR/bin" "$HOME_DIR/models" "$HOME_DIR/src"
    if [ ! -d "$HOME_DIR/src/whisper.cpp" ]; then
      git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$HOME_DIR/src/whisper.cpp"
    fi
    cd "$HOME_DIR/src/whisper.cpp"
    HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" \
      cmake -S . -B build -DGGML_HIP=ON -DAMDGPU_TARGETS="$GPU_ARCH" -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j "$(nproc)"
    cp build/bin/whisper-cli "$HOME_DIR/bin/"
    cp build/bin/libggml*.so* build/bin/libwhisper.so* "$HOME_DIR/bin/" 2>/dev/null || true
    # 途中で止めても壊れたモデルが残らないよう、完了してから置き換える
    # (中途半端なファイルがあるとエンジンが「使える」と誤判定してしまう)
    if [ ! -f "$HOME_DIR/models/$MODEL_NAME" ]; then
      curl -L --progress-bar -o "$HOME_DIR/models/$MODEL_NAME.part" \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME"
      mv "$HOME_DIR/models/$MODEL_NAME.part" "$HOME_DIR/models/$MODEL_NAME"
    fi
    set +x
    echo "=== whisper.cpp の準備ができました: $HOME_DIR ==="
    ;;
  sync)
    # torchのwheelはGPUベンダーごとにindexが違う(pyproject.tomlのグループ参照)。
    # 既定はrocm(default-groups)。NVIDIA機: WL_TORCH_GROUP=cu128 ./dev.sh sync
    if [ "${WL_TORCH_GROUP:-rocm}" = "rocm" ]; then
      exec uv sync
    else
      exec uv sync --no-default-groups --group dev --group "${WL_TORCH_GROUP}"
    fi
    ;;
  check)
    echo "=== backend: pytest ==="
    uv run pytest -q
    echo "=== frontend: typecheck / lint / test / build ==="
    (cd frontend && npm run check)
    echo "=== 全て通りました ==="
    ;;
  all)
    uv run uvicorn backend.app:app --reload --port 8000 &
    API_PID=$!
    trap 'kill $API_PID 2>/dev/null || true' EXIT
    cd frontend && npm run dev
    ;;
  *)
    echo "使い方: ./dev.sh [all|api|web|sync|whispercpp|e2e|check]" >&2
    exit 1
    ;;
esac
