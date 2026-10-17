# KirinukiStudio

対談・イベント動画から、**字幕つきの切り抜き動画**を作るアプリです。
文字起こし・話者の聞き分け・字幕づくり・切り抜きの書き出しまで、すべてお使いのパソコンの中で行います。
**動画や音声を外部に送信しません**(クラウドのAIを選んだ場合だけ、文字起こしの文章をそのAIに送ります)。

<https://github.com/HayatoShimada/assa_movie>

## はじめての使い方

1. **インストールする** — 下の「インストール」から、お使いのOSのインストーラを入れます
2. **初回設定** — 初めて起動すると案内が出ます。この機体の環境の確認、使うAIの選択、
   追加モデル(話者を聞き分けるモデル・高精度な文字起こしモデル)の取得を順に行います
3. **プロジェクトを作る** — 名前を入れ、元の動画と書き出したい動画の向き
   (横→横 / 横→縦 / 縦→縦 / 縦→横)を選んで「作成」
4. **動画を追加する** — 「動画ファイルを選ぶ」で動画を選びます
5. **文字起こしする** — 「文字起こし」を押して待ちます。終わったら「開く」
6. **手直しする**(任意) — 誤認識は、行をダブルクリック(または鉛筆ボタン)で直せます。
   話者名を押すと名前を変えられます。編集画面のタブでは、AIの提案を確認します
   - **レビュー**: 「それ」「あれ」などが何を指すかをAIが補足します。承認したものだけが字幕に入ります
   - **質問**: 聞き間違えやすい固有名詞をAIが見つけて、正しい表記を尋ねます。
     答えた表記は「名前・用語の辞書」に覚えられ、次の文字起こしから正しく書けるようになります
7. **切り抜く** — **クリップ**タブで「切り抜き候補を探す」を押すと、盛り上がった場面をAIが提案します。
   候補を選んで範囲を調整し、「書き出し」

設定は、ホーム右上の「全体の設定」(すべてのプロジェクト共通)と、
各プロジェクトの「設定」(そのプロジェクトだけ)から変えられます。
8. **できた動画を受け取る** — 保存先は下の「書き出した動画の保存先」を見てください

文字起こしにかかる時間は、機体と動画によって大きく変わります。
参考: Radeon RX 7900 XT(Vulkan)で、74分の対談動画が約23分(うち話者の聞き分けが約18分)。
GPUが無い機体ではさらに時間がかかります。

## 何ができるか

- **文字起こし**: Whisper large-v3 による日本語の文字起こし。句読点つきで、単語ごとの時刻も取ります
  (GPU機は同梱の whisper.cpp、GPUが無い機体は faster-whisper。初回起動時に決まります)
- **話者の聞き分け**: 誰が話しているかを自動で見分けます(2人の対談に最適化)
- **相槌・言い淀みの整理**: 「うん」「なるほど」などの相槌や、「あのー」「なんか」などの
  言い淀みを字幕からだけ外します。元の文字起こしは常に残り、いつでも戻せます
- **指示語の補足**: 「それ」「あれ」が指す内容をAIが `それ(先月のイベント)` の形で補います。
  提案は機械的なチェックを通ったものだけが出て、承認・却下・修正できます
- **固有名詞の確認と辞書**: 誤認識されやすい固有名詞(例: 半導体→反動体)をAIが見つけて質問します。
  答えると全部の出現箇所をまとめて直し、利用者の辞書に覚えて次の文字起こしで使います
- **手での修正**: 文字起こしの行を直接直せます(元の文字起こしは残り、いつでも戻せます)。
  話者名の変更や、行ごとの話者の付け替えもできます
- **読みやすい字幕**: 文節の切れ目で改行し(単語の途中で切りません)、句読点や括弧の禁則も守ります。
  話者ごとの色、フォント・文字色・背景を選べ、縦動画でも横動画でも同じ比率で表示します
- **向きの変換**: 横の動画から縦の切り抜きを作るときは、中央の切り出し(位置を調整可)・
  ぼかし背景・顔に合わせた切り出し(1人なら追従、2人なら上下に分割)から選べます
- **切り抜き**: AIと、笑い・テンポ・掛け合いの特徴から候補を提案。範囲の調整、
  無音や相槌の中抜き、タイトル・フック・ハッシュタグの生成
- **書き出し**: 字幕を焼き込んだ動画を書き出します。GPUのハードウェアエンコードを自動で使います

AIはローカル(Ollama)とクラウド(Gemini / Claude)から選べます。
Ollama を使えば、文章も含めて一切外部に送信しません。

## 動作要件

| 項目 | 要件 |
|---|---|
| OS | Ubuntu 24.04 以降 / macOS 11 以降(Apple Silicon)/ Windows 10 以降 |
| GPU | NVIDIA / AMD / Intel(Vulkan対応)または Apple Silicon。VRAM 8GB以上を推奨。GPUが無くても動きます(低速) |
| AI(どちらか) | [Ollama](https://ollama.com/)(ローカル。VRAMに合ったモデルを入れる)/ Gemini または Claude の APIキー |

- GPUのドライバがあれば動きます。CUDA や ROCm などのランタイムは要りません
- AIを使わなくても、文字起こし・話者の聞き分け・字幕つきの書き出しはできます
  (切り抜き候補の提案・指示語の補足・固有名詞の確認にはAIが要ります)

## インストール

[リリースページ](https://github.com/HayatoShimada/assa_movie/releases)から、
お使いのOSのインストーラを落としてください。

| OS | ファイル | 入れ方 |
|---|---|---|
| Ubuntu / Debian | `.deb` | `sudo apt install ./KirinukiStudio_*.deb` |
| Linux(その他) | `.AppImage` | `chmod +x` して実行。書き出しには別途 ffmpeg が必要です |
| macOS | `.dmg` | Apple Silicon 向け。開いて「アプリケーション」へ入れます |
| Windows | `.exe` または `.msi` | 実行して案内に従います |

アプリメニューに **KirinukiStudio** が登録されます。

- **ffmpeg**(動画の読み書き): Windows版・macOS版はアプリに同梱しています。`.deb` は依存として自動で入ります。
  自分で入れた ffmpeg が PATH にあれば、そちらを優先して使います
- **文字起こしの本体**(whisper.cpp)はアプリに同梱済みで、GPU(Linux・Windows は Vulkan、
  macOS は Metal)で動きます。高精度な文字起こしモデル(3.1GB)は初回設定で取得します
- **macOS版**は Apple の署名と公証を通しているので、そのまま開けます

データ(プロジェクト・取り込んだ動画)の置き場所はOSの標準に従います。

| OS | 置き場所 |
|---|---|
| Linux | `~/.local/share/kirinuki-studio/` |
| macOS | `~/Library/Application Support/kirinuki-studio/` |
| Windows | `%APPDATA%\kirinuki-studio\` |

同梱しているソフトウェアのライセンス表記は [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
アプリからは、ホーム右上の **「全体の設定」→「オープンソースソフトウェア」** で見られます。

## 書き出した動画の保存先

書き出した切り抜きは、**元動画と同じフォルダの中の `exports/`** に保存されます。
ファイル名は `元動画名_開始秒s-終了秒s.mp4` です。

動画の取り込み方によって「元動画のあるフォルダ」が変わります:

- **ファイルパスで登録した場合**: 元動画の隣に `exports/` ができます。
  例: `~/Movies/対談.mov` → `~/Movies/exports/対談_624s-676s.mp4`
- **アプリへドラッグ&ドロップで取り込んだ場合**: 動画はアプリのデータフォルダに
  コピーされるため、書き出しもその中に入ります:

| OS | 保存先 |
|---|---|
| macOS | `~/Library/Application Support/kirinuki-studio/uploads/project_<番号>/exports/` |
| Ubuntu | `~/.local/share/kirinuki-studio/uploads/project_<番号>/exports/` |
| Windows | `%APPDATA%\kirinuki-studio\uploads\project_<番号>\exports\` |

## 開発環境のセットアップ

```bash
git clone https://github.com/HayatoShimada/assa_movie && cd assa_movie

# 1. Python依存(配布物と同じ構成。torchは使いません)
./dev.sh sync                 # = uv sync

# 2. GPU機のみ: 文字起こし本体(whisper.cpp。Vulkan / macOSはMetal)をビルドし、
#    large-v3 モデルを取得する。要 build-essential / libvulkan-dev / glslc
./dev.sh whispercpp

# 3. 話者分離モデル(76MB)
./dev.sh diarize-models

# 4. フロントエンド依存
cd frontend && npm ci && cd ..

# 5. AI: Ollama を入れて、VRAMに合うモデルを pull する(またはアプリの設定でAPIキーを登録)
curl -fsSL https://ollama.com/install.sh | sh
```

起動:

```bash
./dev.sh          # バックエンド(:8000)とフロントエンド(:5173)。ブラウザで http://localhost:5173
./dev.sh app      # デスクトップアプリ(Tauri)として起動
./dev.sh package  # 配布用の .deb / AppImage を作る
```

## 開発

```bash
./dev.sh check    # コミット前の全チェック(pytest / 型 / lint / vitest / build / cargo test / E2E)
./dev.sh e2e      # E2E(FakeLLM・一時DBなのでGPUもAIも不要)
cd frontend && npm run gen:api   # バックエンドのAPIを変えたら型を再生成
```

依存はすべて `uv.lock` / `frontend/package-lock.json` で固定しています。配布物もこのロックの版で作ります。
個別にアップグレードしないでください(TypeScript は API 型の自動生成との互換のため 5.9 に固定)。

設計ドキュメント: [DESIGN.md](docs/DESIGN.md)(概要)/ [BACKEND_DESIGN.md](docs/BACKEND_DESIGN.md) /
[FRONTEND_DESIGN.md](docs/FRONTEND_DESIGN.md) / [V1_PLAN.md](docs/V1_PLAN.md)(経緯と進捗)。
AIで開発を続ける場合の規約は [CLAUDE.md](CLAUDE.md)。

## 既知の制限

- 顔に合わせた切り出しは、クリップの中で固定です(カメラが大きく動くと追従しません)。
  顔が見つからないときはぼかし背景に切り替わります
- 複数のクリップをまとめて書き出す機能はまだありません
- 話者の聞き分けは2人の対談に最適化しています(3人以上は「話者N」と表示)

## ライセンス

[MIT License](LICENSE)。配布物に同梱しているソフトウェアの表記は
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
そのほか使用しているモデル・ライブラリには各自のライセンスがあります:

- Whisper / whisper.cpp / faster-whisper: MIT
- 話者分離モデル: MIT(発話区間 / CNRS)・Apache-2.0(声の特徴量 / 3D-Speaker)
- BudouX(字幕の改行位置): Apache-2.0
- Ollama で使うモデル: 各モデルのライセンスに従います
- 文字起こし対象の動画・音声の権利はユーザーに帰属します
