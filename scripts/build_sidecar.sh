#!/usr/bin/env bash
# Pythonバックエンドを1つの実行ファイルに固める(Tauriのサイドカー)。
#
# 配布物にtorchは入れない。pyproject の [project.dependencies] だけを入れた
# 専用の仮想環境を作ってから固める。開発用の .venv(torch入りで約14GB)を
# そのまま固めると配布物が桁違いに膨らむ。
#
#   ./scripts/build_sidecar.sh
#   → frontend/src-tauri/kirinuki-studio-backend
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_DIR="${KS_BUILD_DIR:-build}"
VENV="$BUILD_DIR/sidecar-venv"
OUT="frontend/src-tauri/kirinuki-studio-backend"

echo "=== 配布用の仮想環境を作る(torchなし) ==="
mkdir -p "$BUILD_DIR"
rm -rf "$VENV"
uv venv --python 3.12 "$VENV"

# [project.dependencies] だけを取り出す(dependency-groupsは開発用なので入れない)
uv run --no-sync python - > "$BUILD_DIR/requirements.txt" <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    print("\n".join(tomllib.load(f)["project"]["dependencies"]))
PY
VIRTUAL_ENV="$VENV" uv pip install -q -r "$BUILD_DIR/requirements.txt" pyinstaller

echo "=== 1ファイルに固める ==="
# --collect-all: 動的importで拾えない同梱データ(ONNXの共有ライブラリ、
# ctranslate2のバイナリ、opencvのカスケードxml)を取りこぼさないため
"$VENV/bin/pyinstaller" \
  --noconfirm --clean --onefile \
  --name kirinuki-studio-backend \
  --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work" --specpath "$BUILD_DIR" \
  --paths "$PWD" \
  --collect-submodules backend \
  --collect-all sherpa_onnx \
  --collect-all ctranslate2 \
  --collect-all cv2 \
  --collect-all anthropic \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import uvicorn.protocols.http.httptools_impl \
  --hidden-import uvicorn.protocols.websockets.websockets_impl \
  scripts/sidecar_main.py

cp "$BUILD_DIR/dist/kirinuki-studio-backend" "$OUT"
# Tauriのサイドカーはターゲットトリプル付きの名前を要求する。
# インストール後は実行ファイルの隣にトリプル無しの名前で置かれるので、
# backend.rs の sidecar_path() がそのまま拾える
TRIPLE="$(rustc -vV | sed -n 's/^host: //p')"
cp "$OUT" "$OUT-$TRIPLE"
echo "=== できました: $OUT ($(du -h "$OUT" | cut -f1)) ==="
echo "    Tauri用: $OUT-$TRIPLE"
