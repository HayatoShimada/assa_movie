# FFmpeg について

KirinukiStudio の macOS 版には FFmpeg(`ffmpeg` / `ffprobe`)を同梱しています。
動画の書き出しと、メディア情報の取得に使っています。

一般に配布されているビルドではなく、**このアプリが使う機能だけに絞って自前でビルド
したもの**です(`scripts/build_ffmpeg_macos.sh`)。有効にしているのは字幕の焼き込み
(libass)と、Apple VideoToolbox によるH.264エンコードだけです。

Homebrew の ffmpeg を使わないのは、ffmpeg 9 系の formula から libass が外され、
字幕の焼き込みができないためです。

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

同梱の `ffmpeg` / `ffprobe` は、同名の別のビルドに差し替えて使えます。
また、PATH が通った場所に FFmpeg があれば、同梱のものより**そちらが優先**されます
(自分でビルドを選んでいる意図を尊重します。ただし libass 入りである必要があります)。

## 対応するソースコードの入手先

- **FFmpeg 本体**: <https://ffmpeg.org/releases/>
  バージョンは `VERSION.txt` の1行目に記載しています。
- **ビルド手順**: 本ソフトウェアのリポジトリの `scripts/build_ffmpeg_macos.sh`
  (configure オプションは `VERSION.txt` の `configuration:` 行にも記録されています)
- **同時にリンクしているライブラリ**: いずれも公式リリースのソースからビルドしています。
  版とライセンスは `THIRD-PARTY-NOTICES.txt` を参照してください。

上記から入手できない場合は、下記へお問い合わせください。本ソフトウェアの配布から
3年間、対応するソースコードを実費で提供します。

- 連絡先: info@85-store.com
- 配布元: <https://github.com/HayatoShimada/assa_movie>

## H.264 の書き出しに使うもの

`h264_videotoolbox`(Apple 純正)だけを使います。ハードウェアエンコードが
使えない機体でも、macOS 側がソフトウェア実装に切り替えて完走します。
GPL の libx264 は入れていません。

音声の AAC は FFmpeg 内蔵のエンコーダを使うため、外部ライブラリを足していません。
