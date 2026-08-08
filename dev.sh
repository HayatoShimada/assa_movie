#!/usr/bin/env bash
# 開発用のまとめて起動スクリプト。
#
#   ./dev.sh          バックエンド(8000)とフロント(5173)を同時起動
#   ./dev.sh api      バックエンドのみ
#   ./dev.sh web      フロントのみ
#   ./dev.sh sync     Python依存の同期(既定はROCm。KS_TORCH_GROUP=cu128 でNVIDIA向け)
#   ./dev.sh whispercpp  whisper.cppをROCm向けにビルド(任意・ASRが約2.6倍速くなる)
#   ./dev.sh diarize-models  話者分離のONNXモデルを取得(pyannoteより約4倍速い・HFトークン不要)
#   ./dev.sh check    型・lint・テスト・ビルドを全部走らせる(コミット前用)
#   ./dev.sh e2e      E2Eテスト(FakeLLM・一時DBなのでGPU/LLM不要)
#   ./dev.sh app      デスクトップアプリ(Tauri)として起動
set -euo pipefail
cd "$(dirname "$0")"

# モデルの置き場所の決め方は backend/core/paths.py だけが持つ(ここで二重定義しない)
cache_dir() { uv run --no-sync python -c 'from backend.core.paths import cache_dir; print(cache_dir())'; }

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
  app)
    # Tauriシェルがバックエンドを空きポートで起動するので、./dev.sh は要らない
    cd frontend && exec npm run app
    ;;
  whispercpp)
    # ROCmで最速のASR(公式Whisperの約2.6倍)。外部ビルドなので任意。
    # 用意されていればエンジン自動選択がこれを使い、無ければ公式版に落ちる。
    # 置き場所は KS_WHISPERCPP_HOME で変更できる(既定: ~/.cache/kirinuki-studio)
    HOME_DIR="${KS_WHISPERCPP_HOME:-$(cache_dir)}"
    GPU_ARCH="${KS_GPU_ARCH:-gfx1100}"
    MODEL_NAME="${KS_GGML_MODEL:-ggml-large-v3.bin}"
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
  diarize-models)
    # 話者分離のONNXモデル(計76MB)。pyannote(torch 14GB・HFトークン必須)の代わりで、
    # 実測で約4倍速く一致率94.8%(docs/V1_PLAN.md M23)。取得すると自動で使われる。
    HOME_DIR="${KS_MODELS_HOME:-$(cache_dir)}"
    SEG_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
    EMB_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"
    mkdir -p "$HOME_DIR/models"
    # 途中で止めても壊れたモデルが残らないよう、完了してから置き換える
    # (中途半端なファイルがあるとエンジンが「使える」と誤判定してしまう)
    if [ ! -f "$HOME_DIR/models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx" ]; then
      curl -L --progress-bar -o "$HOME_DIR/models/seg.tar.bz2.part" "$SEG_URL"
      tar xf "$HOME_DIR/models/seg.tar.bz2.part" -C "$HOME_DIR/models"
      rm -f "$HOME_DIR/models/seg.tar.bz2.part"
    fi
    if [ ! -f "$HOME_DIR/models/speaker-embedding.onnx" ]; then
      curl -L --progress-bar -o "$HOME_DIR/models/speaker-embedding.onnx.part" "$EMB_URL"
      mv "$HOME_DIR/models/speaker-embedding.onnx.part" "$HOME_DIR/models/speaker-embedding.onnx"
    fi
    echo "=== 話者分離モデルの準備ができました: $HOME_DIR/models ==="
    ;;
  sync)
    # torchのwheelはGPUベンダーごとにindexが違う(pyproject.tomlのグループ参照)。
    # 既定はrocm(default-groups)。NVIDIA機: KS_TORCH_GROUP=cu128 ./dev.sh sync
    if [ "${KS_TORCH_GROUP:-rocm}" = "rocm" ]; then
      exec uv sync
    else
      exec uv sync --no-default-groups --group dev --group "${KS_TORCH_GROUP}"
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
    echo "使い方: ./dev.sh [all|app|api|web|sync|whispercpp|diarize-models|e2e|check]" >&2
    exit 1
    ;;
esac
