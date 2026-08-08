#!/usr/bin/env bash
# Windows向けのffmpeg/ffprobeを「このアプリが使う機能だけ」でビルドする。
#
# MSYS2のmingw64シェルで動かす:
#   /c/Users/<you>/AppData/Local/ks-build/msys64/mingw64.exe から
#   ./scripts/build_ffmpeg.sh
#
# なぜ自前でビルドするか:
#   一般に配布されているビルドは約50の外部ライブラリを取り込んでいて、
#   ffmpeg.exe だけで110MBある。必要なのは実際には5つで、それ以外は
#   配布サイズにもライセンス表記の対象にも効いてくるだけだった。
#
# 何を有効にしているか(backend/pipeline/ が実際に使うもの):
#   - libass          字幕の焼き込み(ass= フィルタ)。freetype/fribidi/harfbuzzを連れてくる
#   - libopenh264     ハードウェアが使えない機体向けのH.264ソフトウェアエンコーダ(BSD)
#   - nvenc           NVIDIA。ヘッダだけ要る(実体は実行時にドライバから読む)
#   - mediafoundation h264_mf。Windows標準の経路でAMD/Intel/NVIDIAのGPUを使う
#   これで h264_qsv / h264_amf 専用の実装は要らない(_pick_encoderが列挙に無いものは選ばない)
#
# 音声のAACとH.264のデコードはffmpeg内蔵なので、外部ライブラリは足さない。
#
# ライセンス: 上記はいずれもLGPL v2.1と両立する(libass=ISC, openh264=BSD,
# freetype=FTL, fribidi=LGPLv2.1+, harfbuzz=MIT)。GPLのライブラリ(libx264等)を
# 入れないので、成果物はLGPL v2.1になる。--enable-gpl も --enable-version3 も付けない。
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

FFMPEG_VERSION="${FFMPEG_VERSION:-8.0}"
SRC_DIR="${KS_SRC_DIR:-$HOME/.cache/kirinuki-studio/src}"
BUILD_DIR="$SRC_DIR/ffmpeg-$FFMPEG_VERSION"
OUT_DIR="$REPO_ROOT/frontend/src-tauri/resources/bin"

if ! command -v gcc >/dev/null; then
  echo "gccが見つかりません。MSYS2のmingw64シェルで動かしてください" >&2
  exit 1
fi

mkdir -p "$SRC_DIR" "$OUT_DIR"

if [ ! -d "$BUILD_DIR" ]; then
  echo "=== ソースを取得 (ffmpeg $FFMPEG_VERSION) ==="
  TARBALL="$SRC_DIR/ffmpeg-$FFMPEG_VERSION.tar.xz"
  [ -f "$TARBALL" ] || curl -fL -o "$TARBALL" \
    "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz"
  tar -xf "$TARBALL" -C "$SRC_DIR"
fi

cd "$BUILD_DIR"

if [ ! -f config.h ]; then
  echo "=== configure ==="
  # --disable-autodetect: 環境にたまたま入っているライブラリを勝手に取り込ませない。
  #   「何が入っているか」を明示したものだけに保つ(表記の対象を確定させるため)
  # --disable-network: 入力はローカルのファイルだけ。プロトコル一式は要らない
  ./configure \
    --disable-autodetect \
    --disable-debug \
    --disable-doc \
    --disable-network \
    --disable-devices \
    --disable-ffplay \
    --disable-shared \
    --enable-static \
    --enable-libass \
    --enable-libopenh264 \
    --enable-ffnvcodec \
    --enable-nvenc \
    --enable-mediafoundation \
    --enable-d3d11va \
    --enable-dxva2 \
    --enable-zlib \
    --enable-iconv \
    --enable-runtime-cpudetect \
    --enable-w32threads \
    --pkg-config-flags=--static \
    --extra-ldflags="-static -static-libgcc -static-libstdc++" \
    --extra-libs="-lstdc++"
    # openh264はC++で書かれている。pkg-configの Libs.private に -lstdc++ が
    # 入っていないため、明示しないとconfigureのリンク検査で落ちる
fi

echo "=== ビルド ==="
make -j"$(nproc)"

echo "=== 配置 ==="
cp ffmpeg.exe ffprobe.exe "$OUT_DIR/"
ls -lh "$OUT_DIR"/ffmpeg.exe "$OUT_DIR"/ffprobe.exe

echo "=== ライセンス表記を集める ==="
# 静的リンクなので、取り込んだライブラリの表記も配布物に添える必要がある。
# 何がリンクされたかはpkg-configが知っていて、どのパッケージかはpacmanが知っている。
# 手で書き写すと取りこぼすので、両方に聞いて機械的に集める
LIC_DIR="$REPO_ROOT/frontend/src-tauri/resources/licenses/ffmpeg"
rm -rf "$LIC_DIR"
mkdir -p "$LIC_DIR"
cp "$REPO_ROOT/licenses/LGPL-2.1.txt" "$LIC_DIR/LICENSE.txt"
cp "$REPO_ROOT/licenses/ffmpeg-NOTICE.md" "$LIC_DIR/NOTICE.md"
"$OUT_DIR/ffmpeg.exe" -hide_banner -version > "$LIC_DIR/VERSION.txt"

packages=""
for lib in $(pkg-config --static --libs libass openh264 | tr ' ' '\n' | sed -n 's/^-l//p' | sort -u); do
  for candidate in "/mingw64/lib/lib$lib.a" "/mingw64/lib/lib$lib.dll.a"; do
    [ -f "$candidate" ] || continue
    owner="$(pacman -Qoq "$candidate" 2>/dev/null || true)"
    [ -n "$owner" ] && packages="$packages $owner"
    break
  done
done
packages="$(echo "$packages" | tr ' ' '\n' | sed '/^$/d' | sort -u)"

NOTICES="$LIC_DIR/THIRD-PARTY-NOTICES.txt"
{
  echo "同梱している ffmpeg.exe / ffprobe.exe が静的リンクしているライブラリ"
  echo "========================================================================"
  echo
  echo "ffmpeg 本体は LGPL v2.1 です(同じフォルダの LICENSE.txt)。"
  echo "GPLのライブラリ(libx264等)は入れていません。"
  echo "取り込んでいるライブラリと、それぞれのライセンスは次のとおりです。"
  echo
  for pkg in $packages; do
    version="$(pacman -Q "$pkg" 2>/dev/null | awk '{print $2}')"
    # 出力が翻訳されると項目名が変わるのでロケールを固定する
    license="$(LC_ALL=C pacman -Qi "$pkg" 2>/dev/null | sed -n 's/^Licenses *: //p')"
    printf '  %-40s %-14s %s\n' "$pkg" "$version" "$license"
  done
  echo
  echo "■ 補足"
  echo
  echo "  * gcc (GPL-3.0-or-later と表示されるもの) としてリンクされているのは"
  echo "    libatomic / libgcc / libstdc++ といったランタイムです。これらには"
  echo "    GCC Runtime Library Exception が付いており、GPLでないプログラムに"
  echo "    リンクして配布できます。"
  echo "      https://www.gnu.org/licenses/gcc-exception-3.1.html"
  echo "  * gettext-runtime のうちリンクしているのは libintl (LGPL-2.1-or-later) で、"
  echo "    GPL のツール群は含みません。"
  echo "  * crt / winpthreads は mingw-w64 のランタイムです。"
  echo
  echo
  echo "■ ライセンス本文"
  for pkg in $packages; do
    short="${pkg#mingw-w64-x86_64-}"
    for dir in "/mingw64/share/licenses/$short" "/usr/share/licenses/$short"; do
      [ -d "$dir" ] || continue
      for file in "$dir"/*; do
        [ -f "$file" ] || continue
        echo
        echo "------------------------------------------------------------------------"
        echo "$pkg — $(basename "$file")"
        echo "------------------------------------------------------------------------"
        cat "$file"
      done
      break
    done
  done
} > "$NOTICES"
echo "  $(echo "$packages" | wc -l)件のライブラリを $NOTICES にまとめました"

echo "=== 確認 ==="
"$OUT_DIR/ffmpeg.exe" -hide_banner -version | head -1
echo "-- H264エンコーダ --"
"$OUT_DIR/ffmpeg.exe" -hide_banner -encoders 2>/dev/null | grep -E "h264|aac" || true
echo "-- 字幕フィルタ --"
"$OUT_DIR/ffmpeg.exe" -hide_banner -filters 2>/dev/null | grep -E " ass | subtitles " || true
