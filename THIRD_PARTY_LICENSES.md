# サードパーティのライセンス表記

KirinukiStudio 本体は MIT ライセンスです([LICENSE](LICENSE))。
配布物には次の第三者のソフトウェアを**バイナリのまま同梱**しており、
それぞれのライセンスに従います。

## 同梱しているもの

| コンポーネント | 対象OS | ライセンス | 用途 |
|---|---|---|---|
| [FFmpeg](https://ffmpeg.org/) | Windows | LGPL v2.1 | 動画の書き出し・メディア情報の取得 |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Linux / macOS | MIT | 高速な文字起こし |
| Python の依存パッケージ | 全OS | MIT / BSD / Apache-2.0 ほか | バックエンド(PyInstallerが取り込む) |

### FFmpeg (LGPL v2.1)

一般に配布されているビルドは約50の外部ライブラリを取り込んでいて `ffmpeg.exe` だけで
110MBあり、GPL(libx264入り)でもありました。このアプリが使う機能だけに絞って
自前でビルドしています([scripts/build_ffmpeg.sh](scripts/build_ffmpeg.sh))。
結果として **35MB・LGPL v2.1** になり、表記すべきライブラリも19件に収まっています。

表記の全文とソースコードの入手先は [licenses/ffmpeg-NOTICE.md](licenses/ffmpeg-NOTICE.md)、
ライセンス本文は [licenses/LGPL-2.1.txt](licenses/LGPL-2.1.txt)。
静的リンクしているライブラリの一覧と本文は、ビルド時に機械的に集めて
`THIRD-PARTY-NOTICES.txt` に出力しています(pkg-config と pacman から生成)。

インストール後は、アプリと同じ場所の `licenses/ffmpeg/` に入ります。
アプリ内では **設定タブ →「オープンソースソフトウェア」** から確認できます。

FFmpeg は本体とリンクしておらず、独立した実行ファイルを子プロセスとして
呼び出しているだけです。差し替えも可能です。

### Python の依存パッケージ

バックエンドは PyInstaller で1つの実行ファイルに固めるため、依存パッケージが
成果物に取り込まれます = 実質的な再配布です。配布と同じ仮想環境から機械的に集めて
[licenses/python-THIRD-PARTY-NOTICES.txt](licenses/python-THIRD-PARTY-NOTICES.txt)
に出力しています([scripts/collect_python_licenses.py](scripts/collect_python_licenses.py)、
`scripts/build_sidecar.sh` から自動実行)。

インストール後は `licenses/python/THIRD-PARTY-NOTICES.txt` に入ります。

### whisper.cpp (MIT)

Linux版・macOS版に `whisper-cli` を同梱しています(`scripts/build_whispercpp.sh` が
ソースから作ります)。MIT ライセンスなので、著作権表示とライセンス文の同梱で足ります。

## 同梱していないもの

次のものは**配布物に含めず、利用者の環境で取得**します。再配布していないため、
本ソフトウェアの配布に関する表記義務は生じません。

- 文字起こし・話者分離のモデル(Whisper / pyannote / sherpa-onnx)
  — 設定タブの「セットアップ」から利用者が取得します
- Linux版が依存する ffmpeg — `.deb` の依存としてディストリビューションから入ります
- Ollama・各社のLLM API — 利用者が用意します

## 表記の更新のしかた

どちらも手で書き写さず、実際の配布物から機械的に集めます。取りこぼしを防ぐためです。

```bash
./scripts/build_ffmpeg.sh     # MSYS2のmingw64シェル。ffmpegと同時に表記も生成
./scripts/build_sidecar.sh    # Pythonバックエンド。同時に表記も生成
```

## 残っているもの

- macOS版・AppImage版の ffmpeg 同梱(現在はWindows版のみ。macOSは `brew install ffmpeg`、
  `.deb` はパッケージの依存で解決)
