#!/usr/bin/env bash
# macOS向けのffmpeg/ffprobeを「このアプリが使う機能だけ」でビルドする。
# Windows版(build_ffmpeg.sh)と同じ考え方のmacOS版。
#
# なぜ自前でビルドするか:
#   Homebrewのffmpeg 9はlibassが外されていて、字幕の焼き込み(ass=フィルタ)が
#   必ず失敗する(実測。exit 234)。「brewで入れてください」という案内は
#   もう成り立たないので、Windowsと同じく同梱する。
#
# 何を有効にしているか(backend/pipeline/ が実際に使うもの):
#   - libass        字幕の焼き込み。freetype/fribidi/harfbuzzを連れてくる。
#                   フォントの解決はCoreText(macOS純正)なのでfontconfigは要らない
#   - videotoolbox  H.264エンコード。Apple純正で全Macにあり、ハードウェアが
#                   使えない機体でもOS側がソフトウェア実装で完走する
#   音声のAACとH.264のデコードはffmpeg内蔵なので、外部ライブラリは足さない。
#
# 依存はすべてソースから静的ビルドする。Homebrewのライブラリにリンクすると
# 利用者のMacに同じdylibが無くて起動できない配布物になる。
#
# ライセンス: libass=ISC, freetype=FTL(BSD系), fribidi=LGPLv2.1+, harfbuzz=MIT,
# libpng=libpng license。GPLのライブラリ(libx264等)を入れないので、
# 成果物はffmpeg本体と同じLGPL v2.1になる。--enable-gpl は付けない。
#
#   ./scripts/build_ffmpeg_macos.sh
#   → frontend/src-tauri/resources/bin/{ffmpeg,ffprobe}
#   → frontend/src-tauri/resources/licenses/ffmpeg/
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "このスクリプトはmacOS専用です(Windowsは build_ffmpeg.sh)" >&2
  exit 1
fi
for tool in cmake meson ninja make clang; do
  if ! command -v "$tool" > /dev/null; then
    echo "✗ $tool が見つかりません。`brew install cmake meson ninja` で入れてください" >&2
    exit 1
  fi
done

FFMPEG_VERSION="${FFMPEG_VERSION:-8.0}"
LIBPNG_VERSION="1.6.44"
FREETYPE_VERSION="2.13.3"
FRIBIDI_VERSION="1.0.15"
HARFBUZZ_VERSION="10.1.0"
LIBASS_VERSION="0.17.3"

SRC_DIR="${KS_SRC_DIR:-$HOME/.cache/kirinuki-studio/src}"
PREFIX="$SRC_DIR/ffmpeg-deps-prefix"
OUT_DIR="$REPO_ROOT/frontend/src-tauri/resources/bin"
mkdir -p "$SRC_DIR" "$OUT_DIR"

# 配布先のmacOSバージョンを固定する(ビルド機のOSに引きずられない)
export MACOSX_DEPLOYMENT_TARGET=11.0
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

fetch() {
  # fetch <出力名> <URL...>  最初に取れたものを使う(ミラー対応はWindows版と同じ)
  local out="$SRC_DIR/$1"
  shift
  [ -f "$out" ] && return 0
  local url
  for url in "$@"; do
    echo "  $url"
    curl -fL --retry 3 --retry-delay 5 --connect-timeout 20 -o "$out" "$url" && return 0
    rm -f "$out"
  done
  echo "✗ 取得できませんでした: $out" >&2
  return 1
}

extract() {
  # extract <tarball名> <展開先dir>  展開後のディレクトリ名の揺れを吸収する
  local tarball="$SRC_DIR/$1" dest="$2"
  [ -d "$dest" ] && return 0
  local stage="$dest.stage"
  rm -rf "$stage"
  mkdir -p "$stage"
  tar -xf "$tarball" -C "$stage"
  mv "$stage"/*/ "$dest"
  rm -rf "$stage"
}

# ---- libpng(freetypeが絵文字入りフォント(sbix)のPNGグリフ展開に使う) ----
if [ ! -f "$PREFIX/lib/libpng16.a" ]; then
  echo "=== libpng $LIBPNG_VERSION ==="
  fetch "libpng-$LIBPNG_VERSION.tar.gz" \
    "https://github.com/pnggroup/libpng/archive/refs/tags/v$LIBPNG_VERSION.tar.gz" \
    "https://downloads.sourceforge.net/project/libpng/libpng16/$LIBPNG_VERSION/libpng-$LIBPNG_VERSION.tar.gz"
  extract "libpng-$LIBPNG_VERSION.tar.gz" "$SRC_DIR/libpng-$LIBPNG_VERSION"
  cmake -S "$SRC_DIR/libpng-$LIBPNG_VERSION" -B "$SRC_DIR/libpng-$LIBPNG_VERSION/build" \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_BUILD_TYPE=Release \
    -DPNG_SHARED=OFF -DPNG_STATIC=ON -DPNG_TESTS=OFF -DPNG_TOOLS=OFF
  cmake --build "$SRC_DIR/libpng-$LIBPNG_VERSION/build" -j "$JOBS"
  cmake --install "$SRC_DIR/libpng-$LIBPNG_VERSION/build"
fi

# ---- freetype(harfbuzz無しで先に。相互依存の輪をここで断つ) ----
if [ ! -f "$PREFIX/lib/libfreetype.a" ]; then
  echo "=== freetype $FREETYPE_VERSION ==="
  fetch "freetype-$FREETYPE_VERSION.tar.xz" \
    "https://download.savannah.gnu.org/releases/freetype/freetype-$FREETYPE_VERSION.tar.xz" \
    "https://downloads.sourceforge.net/project/freetype/freetype2/$FREETYPE_VERSION/freetype-$FREETYPE_VERSION.tar.xz"
  extract "freetype-$FREETYPE_VERSION.tar.xz" "$SRC_DIR/freetype-$FREETYPE_VERSION"
  cmake -S "$SRC_DIR/freetype-$FREETYPE_VERSION" -B "$SRC_DIR/freetype-$FREETYPE_VERSION/build" \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$PREFIX" \
    -DBUILD_SHARED_LIBS=OFF \
    -DFT_REQUIRE_PNG=ON -DFT_REQUIRE_ZLIB=ON \
    -DFT_DISABLE_HARFBUZZ=ON -DFT_DISABLE_BROTLI=ON -DFT_DISABLE_BZIP2=ON
  cmake --build "$SRC_DIR/freetype-$FREETYPE_VERSION/build" -j "$JOBS"
  cmake --install "$SRC_DIR/freetype-$FREETYPE_VERSION/build"
fi

# ---- fribidi ----
if [ ! -f "$PREFIX/lib/libfribidi.a" ]; then
  echo "=== fribidi $FRIBIDI_VERSION ==="
  fetch "fribidi-$FRIBIDI_VERSION.tar.xz" \
    "https://github.com/fribidi/fribidi/releases/download/v$FRIBIDI_VERSION/fribidi-$FRIBIDI_VERSION.tar.xz"
  extract "fribidi-$FRIBIDI_VERSION.tar.xz" "$SRC_DIR/fribidi-$FRIBIDI_VERSION"
  (
    cd "$SRC_DIR/fribidi-$FRIBIDI_VERSION"
    ./configure --prefix="$PREFIX" --disable-shared --enable-static --disable-debug
    make -j "$JOBS"
    make install
  )
fi

# ---- harfbuzz(字形の整形。libass 0.17系の必須依存) ----
if [ ! -f "$PREFIX/lib/libharfbuzz.a" ]; then
  echo "=== harfbuzz $HARFBUZZ_VERSION ==="
  fetch "harfbuzz-$HARFBUZZ_VERSION.tar.xz" \
    "https://github.com/harfbuzz/harfbuzz/releases/download/$HARFBUZZ_VERSION/harfbuzz-$HARFBUZZ_VERSION.tar.xz"
  extract "harfbuzz-$HARFBUZZ_VERSION.tar.xz" "$SRC_DIR/harfbuzz-$HARFBUZZ_VERSION"
  # cmakeビルドは.pcを作らないのでmeson。coretextはlibass側で使うので不要
  meson setup "$SRC_DIR/harfbuzz-$HARFBUZZ_VERSION/build" "$SRC_DIR/harfbuzz-$HARFBUZZ_VERSION" \
    --prefix="$PREFIX" --default-library=static --buildtype=release \
    -Dfreetype=enabled -Dcoretext=disabled -Dglib=disabled -Dgobject=disabled \
    -Dcairo=disabled -Dicu=disabled -Dtests=disabled -Ddocs=disabled -Dutilities=disabled
  ninja -C "$SRC_DIR/harfbuzz-$HARFBUZZ_VERSION/build" -j "$JOBS"
  ninja -C "$SRC_DIR/harfbuzz-$HARFBUZZ_VERSION/build" install
fi

# ---- libass ----
if [ ! -f "$PREFIX/lib/libass.a" ]; then
  echo "=== libass $LIBASS_VERSION ==="
  fetch "libass-$LIBASS_VERSION.tar.xz" \
    "https://github.com/libass/libass/releases/download/$LIBASS_VERSION/libass-$LIBASS_VERSION.tar.xz"
  extract "libass-$LIBASS_VERSION.tar.xz" "$SRC_DIR/libass-$LIBASS_VERSION"
  (
    cd "$SRC_DIR/libass-$LIBASS_VERSION"
    # フォントの解決はCoreText。fontconfigを外すことでフォントキャッシュの
    # 生成待ち(初回に数分)も避けられる。
    # libunibreakも外す: configureがHomebrewのdylibを拾って動的リンクし、
    # 利用者のMacで起動できない配布物になる(実測。末尾のotool検査で検出)
    ./configure --prefix="$PREFIX" --disable-shared --enable-static \
      --disable-fontconfig --enable-coretext --disable-libunibreak
    make -j "$JOBS"
    make install
  )
fi

# ---- ffmpeg ----
BUILD_DIR="$SRC_DIR/ffmpeg-macos-$FFMPEG_VERSION"
if [ ! -d "$BUILD_DIR" ]; then
  echo "=== ソースを取得 (ffmpeg $FFMPEG_VERSION) ==="
  fetch "ffmpeg-$FFMPEG_VERSION.tar" \
    "https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n$FFMPEG_VERSION.tar.gz" \
    "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz"
  extract "ffmpeg-$FFMPEG_VERSION.tar" "$BUILD_DIR"
fi

cd "$BUILD_DIR"
if [ ! -f config.h ]; then
  echo "=== configure ==="
  # --disable-autodetect: 環境にたまたま入っているライブラリを勝手に取り込ませない
  # --disable-network: 入力はローカルのファイルだけ
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
    --enable-videotoolbox \
    --enable-zlib \
    --enable-iconv \
    --enable-pthreads \
    --pkg-config-flags=--static \
    --extra-cflags="-I$PREFIX/include" \
    --extra-ldflags="-L$PREFIX/lib"
fi

echo "=== ビルド ==="
make -j "$JOBS"

echo "=== 配置 ==="
cp ffmpeg ffprobe "$OUT_DIR/"
ls -lh "$OUT_DIR/ffmpeg" "$OUT_DIR/ffprobe"

echo "=== ライセンス表記を集める ==="
# 静的リンクなので、取り込んだライブラリの表記も配布物に添える。
# 依存はこのスクリプトがソースからビルドしたものが全てなので、
# それぞれの展開ディレクトリからライセンス本文を機械的に集める
LIC_DIR="$REPO_ROOT/frontend/src-tauri/resources/licenses/ffmpeg"
rm -rf "$LIC_DIR"
mkdir -p "$LIC_DIR"
cp "$REPO_ROOT/licenses/LGPL-2.1.txt" "$LIC_DIR/LICENSE.txt"
cp "$REPO_ROOT/licenses/ffmpeg-NOTICE-macos.md" "$LIC_DIR/NOTICE.md"
"$OUT_DIR/ffmpeg" -hide_banner -version > "$LIC_DIR/VERSION.txt"

NOTICES="$LIC_DIR/THIRD-PARTY-NOTICES.txt"
{
  echo "同梱している ffmpeg / ffprobe が静的リンクしているライブラリ"
  echo "========================================================================"
  echo
  echo "ffmpeg 本体は LGPL v2.1 です(同じフォルダの LICENSE.txt)。"
  echo "GPLのライブラリ(libx264等)は入れていません。"
  echo "取り込んでいるライブラリは次のとおりです(いずれもソースからビルド)。"
  echo
  printf '  %-12s %-10s %s\n' "libpng"   "$LIBPNG_VERSION"   "libpng License"
  printf '  %-12s %-10s %s\n' "freetype" "$FREETYPE_VERSION" "FTL (BSD-style)"
  printf '  %-12s %-10s %s\n' "fribidi"  "$FRIBIDI_VERSION"  "LGPL-2.1-or-later"
  printf '  %-12s %-10s %s\n' "harfbuzz" "$HARFBUZZ_VERSION" "MIT (Old MIT)"
  printf '  %-12s %-10s %s\n' "libass"   "$LIBASS_VERSION"   "ISC"
  echo
  echo "zlib / iconv / 各フレームワーク(VideoToolbox, CoreText等)はmacOS標準の"
  echo "ものを実行時に使います(同梱していません)。"
  echo
  echo "■ ライセンス本文"
  for entry in \
    "libpng-$LIBPNG_VERSION:LICENSE" \
    "freetype-$FREETYPE_VERSION:LICENSE.TXT docs/FTL.TXT" \
    "fribidi-$FRIBIDI_VERSION:COPYING" \
    "harfbuzz-$HARFBUZZ_VERSION:COPYING" \
    "libass-$LIBASS_VERSION:COPYING"
  do
    dir="$SRC_DIR/${entry%%:*}"
    for file in ${entry#*:}; do
      [ -f "$dir/$file" ] || continue
      echo
      echo "------------------------------------------------------------------------"
      echo "${entry%%:*} — $file"
      echo "------------------------------------------------------------------------"
      cat "$dir/$file"
      break
    done
  done
} > "$NOTICES"

echo "=== 確認 ==="
"$OUT_DIR/ffmpeg" -hide_banner -version | head -1
echo "-- H264エンコーダ --"
"$OUT_DIR/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -E "h264|aac" || true
echo "-- 字幕フィルタ --"
"$OUT_DIR/ffmpeg" -hide_banner -filters 2>/dev/null | grep -E " ass | subtitles " || true
# 必須の2つが欠けたビルドを配らない(黙って劣化した配布物が最悪)
"$OUT_DIR/ffmpeg" -hide_banner -filters 2>/dev/null | grep -q " ass " \
  || { echo "✗ assフィルタがありません(libassのリンクに失敗)" >&2; exit 1; }
"$OUT_DIR/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox \
  || { echo "✗ h264_videotoolboxがありません" >&2; exit 1; }
# Homebrew等のdylibにリンクしていたら、利用者のMacで起動できない
if otool -L "$OUT_DIR/ffmpeg" | grep -v "^/tmp\|:" | grep -vE "/usr/lib/|/System/Library/"; then
  echo "✗ システム外のdylibにリンクしています(上記)。静的リンクに失敗" >&2
  exit 1
fi
echo "=== できました ==="
