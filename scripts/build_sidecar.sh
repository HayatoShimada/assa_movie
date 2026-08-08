#!/usr/bin/env bash
# Pythonバックエンドを1つの実行ファイルに固める(Tauriのサイドカー)。
#
# 配布物にtorchは入れない。pyproject の [project.dependencies] だけを入れた
# 専用の仮想環境を作ってから固める。開発用の .venv(torch入りで約14GB)を
# そのまま固めると配布物が桁違いに膨らむ。
#
#   ./scripts/build_sidecar.sh
#   → frontend/src-tauri/kirinuki-studio-backend
#
# 注意: `tauri build` はこのバイナリを再ビルドしない。Pythonを変えたら
# 必ずこれを回すこと(`./dev.sh package` は両方やる)。忘れると古いAPIが
# 入ったまま配布され、新しい画面から404が返る。
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_DIR="${KS_BUILD_DIR:-build}"
VENV="$BUILD_DIR/sidecar-venv"
OUT="frontend/src-tauri/kirinuki-studio-backend"

# Windowsのvenvは bin/ ではなく Scripts/ で、実行ファイルに .exe が付く
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*)
    VENV_BIN="$VENV/Scripts"
    EXE=".exe"
    ;;
  *)
    VENV_BIN="$VENV/bin"
    EXE=""
    ;;
esac

# PyInstallerはネイティブのパス表記を要求する(git bashの /d/... は解釈できない)
REPO_ROOT="$(pwd -W 2>/dev/null || pwd)"

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
"$VENV_BIN/pyinstaller$EXE" \
  --noconfirm --clean --onefile \
  --name kirinuki-studio-backend \
  --distpath "$BUILD_DIR/dist" --workpath "$BUILD_DIR/work" --specpath "$BUILD_DIR" \
  --paths "$REPO_ROOT" \
  --collect-submodules backend \
  --collect-all sherpa_onnx \
  --collect-all ctranslate2 \
  --collect-all cv2 \
  --collect-all anthropic \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import uvicorn.protocols.http.httptools_impl \
  --hidden-import uvicorn.protocols.websockets.websockets_impl \
  scripts/sidecar_main.py

cp "$BUILD_DIR/dist/kirinuki-studio-backend$EXE" "$OUT$EXE"
# Tauriのサイドカーはターゲットトリプル付きの名前を要求する。
# インストール後は実行ファイルの隣にトリプル無しの名前で置かれるので、
# backend.rs の sidecar_path() がそのまま拾える
# rustupは ~/.cargo/bin に入る。呼び出し元のPATH設定に依存しない
export PATH="$HOME/.cargo/bin:$PATH"
TRIPLE="$(rustc -vV | sed -n 's/^host: //p')"
cp "$OUT$EXE" "$OUT-$TRIPLE$EXE"
echo "=== できました: $OUT$EXE ($(du -h "$OUT$EXE" | cut -f1)) ==="
echo "    Tauri用: $OUT-$TRIPLE$EXE"
