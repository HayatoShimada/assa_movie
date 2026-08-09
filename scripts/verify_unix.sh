#!/usr/bin/env bash
# Linux(.deb / .AppImage)とmacOS(.dmg)のインストーラを実機で検証する。
#
# verify_windows.ps1 のLinux/macOS版。**この3つは一度もインストール・起動
# されずに配布されていた**。ビルドが通ることと動くことは別問題で、
# v0.9.2はWindows版で実際にそうなった。
#
#   ./scripts/verify_unix.sh path/to/KirinukiStudio.AppImage
#   ./scripts/verify_unix.sh path/to/kirinuki-studio_0.9.8_amd64.deb
#   ./scripts/verify_unix.sh path/to/KirinukiStudio.dmg
#
# 終了コード 0 = 全項目OK。CIの各ランナーでもそのまま回せる。
#
# GUIの無いランナーでも通るよう、確かめるのは「バックエンドが動くか」に絞る。
# Tauriのwebviewはヘッドレスでは開けないので、シェルではなく同梱の
# サイドカーを直接起動して検証する(利用者が踏む経路と同じバイナリ)。
set -uo pipefail

FAILURES=0
step() { printf '\n\033[36m=== %s ===\033[0m\n' "$1"; }
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()   { printf '  \033[31mNG\033[0m   %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
info() { printf '       %s\n' "$1"; }

PACKAGE="${1:-}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---- 1. 展開 -------------------------------------------------------------
step "1. 展開"
if [ -z "$PACKAGE" ]; then
  echo "使い方: $0 <.deb | .AppImage | .dmg>" >&2
  exit 2
fi
[ -f "$PACKAGE" ] || { echo "パッケージが見つかりません: $PACKAGE" >&2; exit 2; }

ROOT=""   # 同梱物(bin/ models/ licenses/)のルート
SIDECAR=""

# 置き場所はTauriのバンドラが決める。**サイドカーと同梱物は別の場所に入る**
# (Linuxのdebは実行ファイルが /usr/bin、リソースが /usr/lib/<製品名>)。
# サイドカーの隣をルートとみなしていたら、同梱物が1つも見つからなかった。
# 決め打ちもしない(製品名を変えたときに黙って空振りする)。
# 「必ず同梱するもの」を目印にして、そこからルートを逆算する。
ROOT_ANCHORS=(
  "licenses/python/THIRD-PARTY-NOTICES.txt"
  "models/speaker-embedding.onnx"
  "bin/whisper-cli"
)

find_layout() {
  local tree="$1" anchor hit depth
  SIDECAR="$(find "$tree" -name "kirinuki-studio-backend*" -type f -print -quit 2>/dev/null)"

  for anchor in "${ROOT_ANCHORS[@]}"; do
    hit="$(find "$tree" -path "*/$anchor" -print -quit 2>/dev/null)"
    [ -n "$hit" ] || continue
    # 目印の階層ぶんだけ上がるとリソースのルートになる
    ROOT="$hit"
    depth=$(tr -cd '/' <<< "$anchor" | wc -c)
    for _ in $(seq 0 "$depth"); do ROOT="$(dirname "$ROOT")"; done
    return 0
  done
  return 1
}

case "$PACKAGE" in
  *.deb)
    dpkg-deb -x "$PACKAGE" "$WORK/root"
    ok "展開: $(du -sh "$WORK/root" | cut -f1)"
    find_layout "$WORK/root" || ng "同梱物が見つからない(.deb の中身が想定と違う)"
    ;;
  *.AppImage)
    chmod +x "$PACKAGE"
    PACKAGE_ABS="$(cd "$(dirname "$PACKAGE")" && pwd)/$(basename "$PACKAGE")"
    (cd "$WORK" && "$PACKAGE_ABS" --appimage-extract > /dev/null)
    ok "展開: $(du -sh "$WORK/squashfs-root" | cut -f1)"
    find_layout "$WORK/squashfs-root" || ng "同梱物が見つからない(AppImageの中身が想定と違う)"
    ;;
  *.dmg)
    MOUNT="$WORK/mnt"
    mkdir -p "$MOUNT"
    hdiutil attach "$PACKAGE" -nobrowse -readonly -mountpoint "$MOUNT" > /dev/null
    trap 'hdiutil detach "$MOUNT" >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT
    app="$(find "$MOUNT" -maxdepth 1 -name "*.app" -print -quit)"
    [ -n "$app" ] || { ng ".app が見つかりません"; exit 1; }
    ok "マウント: $(basename "$app")"
    # macOSはサイドカーが MacOS/、リソースが Resources/ と別の場所になる
    SIDECAR="$app/Contents/MacOS/kirinuki-studio-backend"
    ROOT="$app/Contents/Resources"
    ;;
  *)
    echo "対応していない形式です: $PACKAGE" >&2
    exit 2
    ;;
esac

# ---- 2. 同梱物 -----------------------------------------------------------
step "2. 同梱物"
[ -x "$SIDECAR" ] && ok "サイドカー: $(du -h "$SIDECAR" | cut -f1)" \
                  || ng "サイドカーが無い/実行できない: $SIDECAR"

# ライセンス表記は再配布の条件そのもの。欠けたら配ってはいけない。
# whisper.cpp の表記は .ps1 にしか生成処理が無く、Linux/macOSでは
# 長らく欠けていた(MITの条件未充足)
BUNDLED=(
  "bin/whisper-cli"
  "models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
  "models/speaker-embedding.onnx"
  "licenses/whispercpp/LICENSE.txt"
  "licenses/whispercpp/VERSION.txt"
  "licenses/diarization/LICENSE-segmentation.txt"
  "licenses/diarization/LICENSE-embedding-Apache-2.0.txt"
  "licenses/diarization/NOTICE.md"
  "licenses/python/THIRD-PARTY-NOTICES.txt"
)
for rel in "${BUNDLED[@]}"; do
  if [ -f "$ROOT/$rel" ]; then
    ok "同梱: $rel ($(du -h "$ROOT/$rel" | cut -f1))"
  else
    ng "同梱物が無い: $rel"
  fi
done

# 実行ビットが落ちていると、例外にならず黙ってfaster-whisper(CPU)へ降格する。
# 「遅くなっただけ」に見えるので誰も気付かない
if [ -f "$ROOT/bin/whisper-cli" ]; then
  [ -x "$ROOT/bin/whisper-cli" ] && ok "whisper-cli に実行ビットがある" \
                                 || ng "whisper-cli の実行ビットが落ちている"
fi

# ---- 3. 起動と疎通 -------------------------------------------------------
step "3. 起動と疎通"
if [ ! -x "$SIDECAR" ]; then
  info "サイドカーが無いので疎通確認はスキップ"
else
  PORT=18765
  # 本番と同じ環境変数を与える。同梱物の場所はこれで決まる(core/bundled.py)
  KS_RESOURCE_DIR="$ROOT" \
  KS_DB_PATH="$WORK/verify.db" \
    "$SIDECAR" --port "$PORT" > "$WORK/backend.log" 2>&1 &
  BACKEND_PID=$!

  BASE="http://127.0.0.1:$PORT"
  for _ in $(seq 1 60); do
    curl -sf "$BASE/api/health" > /dev/null 2>&1 && break
    kill -0 "$BACKEND_PID" 2>/dev/null || break
    sleep 1
  done

  if curl -sf "$BASE/api/health" > /dev/null 2>&1; then
    ok "GET /api/health => $(curl -s "$BASE/api/health")"

    # ---- 同梱物が「使えるか」をバックエンドに解決させる ----
    # ファイルの存在検査では足りない。v0.9.6はwhisper.cppを同梱したのに
    # エンジン選択がそれを選ばず、同梱した意味が無かった
    setup="$(curl -s "$BASE/api/setup")"
    case "$setup" in
      *'"diarization"'*'"ready":true'*) ok "話者分離モデルが使える" ;;
      *) ng "話者分離が未準備: $setup" ;;
    esac

    env_json="$(curl -s --max-time 60 "$BASE/api/environment")"
    info "環境: $(echo "$env_json" | head -c 400)"

    # **ffmpegはLinux/macOSには同梱していない**(.debは依存宣言、macOSはbrew)。
    # 検証機に入っているかどうかは配布物の問題ではないので、NGにはしない。
    # ここで見たいのは「同梱していないものを同梱物として探していないか」だけ
    case "$env_json" in
      *'"ffmpeg":true'*) ok "ffmpeg を見つけている" ;;
      *) info "ffmpeg はこの機体に入っていない(同梱対象外。書き出し時に案内が出る)" ;;
    esac
  else
    ng "バックエンドが応答しない"
    info "--- backend.log ---"
    sed -n '1,60p' "$WORK/backend.log" || true
  fi

  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true

  sleep 1
  if pgrep -f "kirinuki-studio-backend" > /dev/null 2>&1; then
    ng "バックエンドが残っている"
    pkill -f "kirinuki-studio-backend" || true
  else
    ok "残留プロセスなし"
  fi
fi

# ---- 4. まとめ -----------------------------------------------------------
step "4. まとめ"
if [ "$FAILURES" -eq 0 ]; then
  ok "全項目OK"
  exit 0
fi
ng "$FAILURES 件の問題があります"
exit 1
