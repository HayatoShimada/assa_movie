# サードパーティのライセンス表記

KirinukiStudio 本体は MIT ライセンスです([LICENSE](LICENSE))。
配布物には次の第三者のソフトウェアを**バイナリのまま同梱**しており、
それぞれのライセンスに従います。

## 同梱しているもの

| コンポーネント | 対象OS | ライセンス | 用途 |
|---|---|---|---|
| [FFmpeg](https://ffmpeg.org/) | Windows | LGPL v2.1 | 動画の書き出し・メディア情報の取得 |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | Linux / macOS / Windows | MIT | 高速な文字起こし |
| 話者分離モデル(ONNX) | 全OS | MIT / Apache-2.0 | だれが話しているかの判定 |
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

### 話者分離モデル (MIT / Apache-2.0)

発話区間の検出(pyannote segmentation-3.0 を ONNX 化。MIT / CNRS)と、話者の
特徴量(3D-Speaker eres2netv2 を ONNX 化。Apache-2.0)の2つを同梱しています。
詳細は [licenses/diarization-NOTICE.md](licenses/diarization-NOTICE.md)。

配布物には PyTorch を入れていないため、torch を使う pyannote エンジンは
インストール版では動きません。ONNX が唯一使えるエンジンなので、モデルを
同梱しないと話者分離がまったく使えなくなります。

取得は [scripts/fetch_diarization_models.sh](scripts/fetch_diarization_models.sh)
(Windows は `.ps1`)。インストール後は `licenses/diarization/` に入ります。

### Python の依存パッケージ

バックエンドは PyInstaller で1つの実行ファイルに固めるため、依存パッケージが
成果物に取り込まれます = 実質的な再配布です。配布と同じ仮想環境から機械的に集めて
[licenses/python-THIRD-PARTY-NOTICES.txt](licenses/python-THIRD-PARTY-NOTICES.txt)
に出力しています([scripts/collect_python_licenses.py](scripts/collect_python_licenses.py)、
`scripts/build_sidecar.sh` から自動実行)。

インストール後は `licenses/python/THIRD-PARTY-NOTICES.txt` に入ります。

### whisper.cpp (MIT)

3OSすべてに `whisper-cli` を同梱しています。ソースからビルドします
(Linux・macOS は [scripts/build_whispercpp.sh](scripts/build_whispercpp.sh)、
Windows は [scripts/build_whispercpp.ps1](scripts/build_whispercpp.ps1))。

バックエンドはOSで変えています。Linux・Windows は **Vulkan**、macOS は **Metal**。
Vulkanのローダー(`vulkan-1.dll` 等)はGPUドライバが提供するため、同梱物には含みません。

MIT ライセンスなので著作権表示とライセンス文の同梱で足ります。インストール後は
`licenses/whispercpp/` に入ります(ビルドしたコミットも `VERSION.txt` に記録)。

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
