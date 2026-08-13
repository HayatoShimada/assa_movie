# CLAUDE.md

このリポジトリでAIがコードを書くときの規約。設計書は [DESIGN.md](docs/DESIGN.md) /
[BACKEND_DESIGN.md](docs/BACKEND_DESIGN.md) / [FRONTEND_DESIGN.md](docs/FRONTEND_DESIGN.md) /
[V1_PLAN.md](docs/V1_PLAN.md)。**迷ったら設計書が正**。

## これは何か

対談動画から文字起こし・話者分離・字幕生成を行い、切り抜き動画を作るローカルアプリ。
Tauri(Rust)+ React + Python/FastAPI で、3OS向けのインストーラを配布している。

## よく使うコマンド

```bash
./dev.sh              # バックエンド(8000)+フロント(5173)を起動
./dev.sh app          # デスクトップアプリ(Tauri)として起動
./dev.sh package      # 配布用の .deb / AppImage を作る
                      # (tauri build 単体ではPythonサイドカーが再ビルドされない)
./dev.sh check        # コミット前の全チェック(pytest + typecheck + lint + vitest + build)
./dev.sh e2e          # E2E(FakeLLM・一時DBなのでGPUもOllamaも不要)
./dev.sh whispercpp   # GPU機のASR本体(Vulkan/Metal)をビルド+ggmlモデル取得
                      # 要 build-essential / libvulkan-dev / glslc

# macOS
./scripts/build_ffmpeg_macos.sh                   # 同梱ffmpegをビルド(libass+VideoToolbox)
                                                  # 要 cmake / meson / ninja。brewのffmpegは
                                                  # libass無しで字幕焼き込みが失敗するので使わない

# Windows
./scripts/build_ffmpeg.sh                         # 同梱ffmpegをビルド(MSYS2のmingw64シェル)
./scripts/build_whispercpp.ps1                    # 同梱whisper.cpp(Vulkan)をビルド
./scripts/package_windows.ps1                     # Windows版を手元で梱包する
./scripts/verify_windows.ps1 -Installer <path>    # 入れて・起動して・閉じるまで検証

uv run --no-project python scripts/fetch_diarization_models.py   # 話者分離モデル(3OS共通)
./scripts/verify_unix.sh <.deb|.AppImage|.dmg>    # Linux/macOS版の実機検証

uv run pytest -q                  # バックエンドのテスト
uv run pytest -q --run-gpu        # GPUを使うgolden検証も含める(約10秒)
cd frontend && npm run gen:api    # バックエンドのAPIを変えたら必ず実行(型を再生成)
```

## 開発の型(必ず守る)

1. **テストを先に書く。** 期待する振る舞いをテストで表明してから実装する。
2. **LLMを使う機能は必ず `FakeLLMClient` でテストする。** 実LLMに依存したテストを書かない
   (`backend/engines/llm/base.py`)。実LLMでの確認は最後に手動で1回。
3. **APIを変えたら `npm run gen:api`。** 型が自動生成されるので、追従漏れは型エラーで分かる。
4. **純関数に寄せる。** 判定・整形・プロンプト合成はDBやHTTPから切り離してテーブル駆動テストにする
   (例: `backend/pipeline/pronoun.py`)。
5. **UIを変えたらE2Eも足す。** `frontend/e2e/` に画面操作のテストを書く。
6. **日本語を出力するPythonは標準出力をUTF-8に固定する**(`backend/core/console.py` の
   `force_utf8_stdio()`)。Windowsの既定は日本語環境がcp932・CIの英語環境がcp1252で、
   どちらも「⚠」や日本語でUnicodeEncodeErrorになりプロセスごと落ちる。
   **入力側も同じ**。子プロセスの出力は `SUBPROCESS_TEXT` を展開して渡し、
   ファイルは `encoding="utf-8"` を必ず明示する。
   同じ根で5回落としている(v0.9.2の起動 / v0.9.3のCIビルド / v0.9.6のwhisper-cli /
   CIの英語Windowsで日本語が**書けない**件)。ASTのガードテストで見張っている
   (`tests/core/test_encoding.py`)。
7. **CIの緑をもってマージ可能とする。** `.github/workflows/ci.yml` が3OSで
   pytest・フロント・cargo test・E2Eを回す。「手元で流したから大丈夫」で進めない。

## 設計上の重要な決定(変えるときは相談)

- **実行環境は初回起動で1回検出して固定する(`backend/core/hwprofile.py`)。**
  OS(linux/windows/mac)×GPU(nvidia/radeon/apple/cpu)だけをDBに保存し、
  「プロファイル→実行構成」の対応表はコードが持つ(アプリ更新で自動追従する)。
  GPU機はベンダーを問わず whisper.cpp(Vulkan / macOSはMetal)、CPU機は
  faster-whisper(int8)。**実行時に環境を判定しない・フォールバックしない。**
  構成が壊れていたら直し方を添えてエラーで止める。環境が変わったときの追従は
  設定タブの「再検出」だけ。エンジン名を設定に保存してはいけない
  (v0.9.5でそれをやり、whisper.cpp同梱後もGPUが使われないままになった)。
  モデルは large-v3 が既定(精度優先・単語タイムスタンプ必須。BACKEND_DESIGN.md)。
- **whisper.cppは `--output-json-full` で呼ぶ(`-ml` を付けない)。**
  句読点・トークンのタイムスタンプ・確率が一度に取れる。`-ml` を付けると
  句読点が落ちる(実測)。セグメント分割は `engines/asr/segmenting.py` で自前に行う。
- **torchは使わない(2026-08-10に完全に外した)。** ASRはwhisper.cppと
  faster-whisper(CTranslate2)、話者分離はsherpa-onnx、ピッチ推定は自前numpy実装。
  開発環境と配布物の構成が一致していること自体が仕様。torchを足すと
  「開発機では再現しない」不具合が戻ってくるので、入れるときは相談。
  依存バージョンは固定(TypeScript 5.9)。上げない。
- **同梱するwhisper.cppは必ずGPUバックエンド(Vulkan/Metal)。**
  ビルドスクリプトはglslcが無ければ失敗し、できたバイナリのリンク先も確認する。
  CPUビルドが混ざると「GPU機なのに遅い」配布物になり、実行するまで気付けない。
- **設定は3層(グローバル→プロジェクト→クリップ)。** ジョブ・APIは
  `resolve_settings()`(backend/core/project_settings.py)経由で読む。
  ジョブ層でグローバルsettingsを直接importしない(テストで担保)。
- **字幕のpx値は1920×1080基準で保存し、出力解像度へ比率換算する。**
  フォント・左右余白=幅比率、上下余白=高さ比率(subtitle.scaled_style)。
  フロントのプレビューも同じ規則(cqw/cqh)で描く。
- **LLMは提案するだけ、適用は機械ガードを通ったものだけ。**
  `pronoun.validate_edit()` が削除のみ・既出重複・慣用表現などを弾く。この構造を壊さない。
- **配布物にtorchを入れない。** torchだけで11.5GB、入れないと644MB。
  `[project.dependencies]` はtorch非依存のものだけにし、torch系は
  `[dependency-groups] torch-engines`(開発専用)に置く。
  GPU検出もtorchではなく `rocm-smi`/`nvidia-smi`(Windowsはレジストリ)から読む
  (torchに聞くと5秒、CLIなら120ms。`backend/core/device.py`)。
  **配布版で動かないエンジンは選択肢に置かない。** 「選べるのに選ぶと落ちる」に
  なるため、transformers版Whisperとpyannoteは削除した(2026-08-09)。
- **効いていない設定をUIに出さない。** Settings に無い項目、バックエンドが読んで
  いない項目は消す。「切ったのに効かない」は利用者にも実装にも嘘をつくことになる。
- **同梱物の場所は `backend/core/bundled.py` だけが決める。** パッケージ形式で
  変わるので自分で組み立てず、Tauriシェルが `KS_RESOURCE_DIR` で教えてくれた場所を使う。
- **バイナリを同梱したら、同じOSのconfにライセンス表記も足す。**
  `frontend/src-tauri/tauri.<os>.conf.json` が対応表。欠けたら再配布の条件を満たさない。
- **`original_text` は常に原文を保持。** 置換もユーザー編集も非破壊で、いつでも戻せる。
- **指示語置換の既定は `annotate`(カッコ注釈)。** 発言を改変しないため最も安全。

## ディレクトリ

```
backend/
  api/        FastAPIルーター(projects, jobs, transcripts, edits, questions, settings)
  core/       設定(UIの設定タブと1対1対応)
  engines/    ASR / 話者分離 / LLM の差し替え可能な実装
  jobs/       ジョブキュー(単一ワーカー直列)とジョブ本体
  models/     SQLiteスキーマとDTO
  pipeline/   音声デコード・相槌判定・指示語置換・字幕整形(純関数中心)
  e2e_server.py  E2E用サーバー(FakeLLM・一時DB・シードAPI)
frontend/
  src/api/    型付きクライアント(schema.d.tsは自動生成物なので手で編集しない)
  src-tauri/  デスクトップシェル(Rust)。Pythonを子プロセスで起動するだけで画面は持たない
  e2e/        Playwright
scripts/      同梱物のビルド・取得・実機検証
tests/
  core/       設定・パス・デバイス検出・ライセンス
  engines/    ASR / 話者分離 / LLM
  pipeline/   純関数(golden/ に移植前の出力を保存し回帰検証)
  api/        HTTP経由の振る舞い
  fixtures/   PythonとTypeScriptで共有するケース表
  helpers.py  下準備の集約(プロジェクト作成・FakeLLMの差し替え)
```

## 日本語UI・日本語コード

- コメント・コミットメッセージ・UI文言は日本語。
- テストケース名も日本語で書いてよい(`test_〜` の中身は日本語文字列でOK)。
- 相槌・フィラー・指示語の判定は日本語特有なので、テストケースを削らない・短縮しない
  (短縮すると意図が変わる。`tests/test_m1_pipeline.py` のコメント参照)。
