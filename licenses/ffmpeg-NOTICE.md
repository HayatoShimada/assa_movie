# FFmpeg について

KirinukiStudio の Windows 版には FFmpeg(`ffmpeg.exe` / `ffprobe.exe`)を同梱しています。
動画の書き出しと、メディア情報の取得に使っています。

一般に配布されているビルドではなく、**このアプリが使う機能だけに絞って自前でビルド
したもの**です(`scripts/build_ffmpeg.sh`)。有効にしているのは字幕の焼き込み(libass)、
ソフトウェアH.264エンコード(libopenh264)、NVIDIA NVENC、Windows Media Foundation
だけです。

## ライセンス

同梱している FFmpeg は **GNU Lesser General Public License (LGPL) version 2.1**
のもとで配布されています。GPL のライブラリ(libx264 など)は含めていないため、
GPL ではありません。全文と内訳は同じフォルダにあります。

| ファイル | 内容 |
|---|---|
| `LICENSE.txt` | LGPL version 2.1(FFmpeg 本体) |
| `THIRD-PARTY-NOTICES.txt` | 静的リンクしている全ライブラリの一覧とライセンス本文 |
| `VERSION.txt` | バージョンと configure オプション |
| `NOTICE.md` | この文書 |

FFmpeg は KirinukiStudio 本体とリンクしていません。独立した実行ファイルを
子プロセスとして呼び出しているだけです。KirinukiStudio 本体は MIT ライセンスです。

同梱の `ffmpeg.exe` / `ffprobe.exe` は、同名の別のビルドに差し替えて使えます。
また、PATH が通った場所に FFmpeg があれば、同梱のものより**そちらが優先**されます。

## 対応するソースコードの入手先

- **FFmpeg 本体**: <https://ffmpeg.org/releases/>
  バージョンは `VERSION.txt` の1行目に記載しています。
- **ビルド手順**: 本ソフトウェアのリポジトリの `scripts/build_ffmpeg.sh`
  (configure オプションは `VERSION.txt` の `configuration:` 行にも記録されています)
- **同時にリンクしているライブラリ**: いずれも MSYS2 の mingw-w64 パッケージです。
  版とライセンスは `THIRD-PARTY-NOTICES.txt` を参照してください。
  <https://packages.msys2.org/>

上記から入手できない場合は、下記へお問い合わせください。本ソフトウェアの配布から
3年間、対応するソースコードを実費で提供します。

- 連絡先: info@85-store.com
- 配布元: <https://github.com/HayatoShimada/assa_movie>

## H.264 の書き出しに使うもの

GPL の libx264 を入れていないため、H.264 の書き出しは次の順で選びます
(`backend/pipeline/export.py` の `_pick_encoder`)。

1. `h264_nvenc` — NVIDIA。ドライバがある機体のみ
2. `h264_mf` — Windows 標準の Media Foundation。AMD・Intel の GPU もこの経路で使う
3. `libopenh264` — ソフトウェア(BSD-2-Clause)。上記が使えない機体向け

音声の AAC は FFmpeg 内蔵のエンコーダを使うため、外部ライブラリを足していません。
