#!/usr/bin/env bash
# 開発用のまとめて起動スクリプト。
#
#   ./dev.sh          バックエンド(8000)とフロント(5173)を同時起動
#   ./dev.sh api      バックエンドのみ
#   ./dev.sh web      フロントのみ
#   ./dev.sh sync     Python依存の同期(配布物と同じ構成。GPUベンダーに依らない)
#   ./dev.sh whispercpp  whisper.cpp(Vulkan/Metal)をビルド+モデル取得。GPU機のASR本体
#   ./dev.sh diarize-models  話者分離のONNXモデルを取得(pyannoteより約4倍速い・HFトークン不要)
#   ./dev.sh check    型・lint・テスト・ビルドを全部走らせる(コミット前用)
#   ./dev.sh e2e      E2Eテスト(FakeLLM・一時DBなのでGPU/LLM不要)
#   ./dev.sh app      デスクトップアプリ(Tauri)として起動
#   ./dev.sh package  配布用パッケージ(.deb / AppImage)を作る
set -euo pipefail
cd "$(dirname "$0")"

# OneDrive配下ではハードリンクが張れず uv sync が os error 396 で落ちる。
# コピーは少し遅いだけでどのOSでも安全なので常に指定する
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

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
  package)
    # Pythonを1ファイルに固めてからTauriでパッケージする。
    # 配布物にtorchは入れない(scripts/build_sidecar.sh 参照)
    # cargo/rustcはrustupの既定の場所に入る
    export PATH="$HOME/.cargo/bin:$PATH"
    ./scripts/build_sidecar.sh
    ./scripts/build_whispercpp.sh
    # resources/ は丸ごとgitignoreなので、クリーンチェックアウトでは
    # モデルが存在せず tauri build がリソース不足で落ちる。
    # CIは別経路(release.yml)で取っていたため、この穴を踏まなかった
    uv run --no-project python scripts/fetch_diarization_models.py
    # macOSで署名情報があれば、同梱バイナリにも署名する(公証の要件)
    [ "$(uname -s)" = "Darwin" ] && ./scripts/sign_macos_binaries.sh
    cd frontend && exec npm run app:build
    ;;
  app)
    # Tauriシェルがバックエンドを空きポートで起動するので、./dev.sh は要らない
    cd frontend && exec npm run app
    ;;
  whispercpp)
    # GPU機のASR本体。配布物と同じVulkan(macOSはMetal)ビルドを作り、
    # 開発機でも本番と同じものが動くようにする。
    # ベンダー別ビルド(HIP等)は作らない: 配布物と違うものを開発機だけで
    # 動かすと、実測も不具合も本番に当てはまらなくなる。
    # 置き場所は KS_WHISPERCPP_HOME で変更できる(既定: ~/.cache/kirinuki-studio)
    HOME_DIR="${KS_WHISPERCPP_HOME:-$(cache_dir)}"
    MODEL_NAME="${KS_GGML_MODEL:-ggml-large-v3.bin}"
    mkdir -p "$HOME_DIR/bin" "$HOME_DIR/models"
    # ビルド本体は配布と同じスクリプトを使う(Vulkan必須・リンク確認つき)
    ./scripts/build_whispercpp.sh
    cp frontend/src-tauri/resources/bin/whisper-cli "$HOME_DIR/bin/"
    chmod +x "$HOME_DIR/bin/whisper-cli"
    # 途中で止めても壊れたモデルが残らないよう、完了してから置き換える
    # (中途半端なファイルがあるとエンジンが「使える」と誤判定してしまう)
    if [ ! -f "$HOME_DIR/models/$MODEL_NAME" ]; then
      curl -L --progress-bar -o "$HOME_DIR/models/$MODEL_NAME.part" \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME"
      mv "$HOME_DIR/models/$MODEL_NAME.part" "$HOME_DIR/models/$MODEL_NAME"
    fi
    echo "=== whisper.cpp の準備ができました: $HOME_DIR ==="
    echo "設定タブの「実行環境」で「再検出」すると反映されます"
    ;;
  diarize-models)
    # 話者分離のONNXモデル(計76MB)。pyannote(torch 14GB・HFトークン必須)の代わりで、
    # 実測で約4倍速く一致率94.8%(docs/V1_PLAN.md M23)。取得すると自動で使われる。
    # URLと置き場所は backend/engines/diarize/model_sources.py だけが持つ
    exec uv run --no-project python scripts/fetch_diarization_models.py \
      --home "${KS_MODELS_HOME:-$(cache_dir)}" "${@:2}"
    ;;
  sync)
    # 依存はGPUベンダーに依らない(torchを使わなくなったため)。
    # 実行構成は backend/core/hwprofile.py の対応表が決める
    exec uv sync
    ;;
  check)
    # CI(.github/workflows/ci.yml)と同じものを手元で流す。
    # cargo testとE2Eが入っていなかったため、Rustの12件は誰も実行しておらず、
    # E2Eは壊れても気付けなかった
    echo "=== backend: pytest ==="
    uv run pytest -q
    echo "=== frontend: typecheck / lint / test / build ==="
    (cd frontend && npm run check)
    echo "=== tauri: cargo test ==="
    PATH="$HOME/.cargo/bin:$PATH" cargo test --manifest-path frontend/src-tauri/Cargo.toml
    echo "=== e2e: playwright ==="
    (cd frontend && npm run e2e)
    echo "=== 全て通りました ==="
    ;;
  all)
    uv run uvicorn backend.app:app --reload --port 8000 &
    API_PID=$!
    trap 'kill $API_PID 2>/dev/null || true' EXIT
    cd frontend && npm run dev
    ;;
  *)
    echo "使い方: ./dev.sh [all|app|package|api|web|sync|whispercpp|diarize-models|e2e|check]" >&2
    exit 1
    ;;
esac
