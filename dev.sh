#!/usr/bin/env bash
# 開発用のまとめて起動スクリプト。
#
#   ./dev.sh          バックエンド(8000)とフロント(5173)を同時起動
#   ./dev.sh api      バックエンドのみ
#   ./dev.sh web      フロントのみ
#   ./dev.sh sync     Python依存の同期(既定はROCm。WL_TORCH_EXTRA=cu128 でNVIDIA向け)
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
    echo "使い方: ./dev.sh [all|api|web|sync|e2e|check]" >&2
    exit 1
    ;;
esac
