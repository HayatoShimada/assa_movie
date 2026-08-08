# CLAUDE.md

このリポジトリでAIがコードを書くときの規約。設計書は [DESIGN.md](docs/DESIGN.md) /
[BACKEND_DESIGN.md](docs/BACKEND_DESIGN.md) / [FRONTEND_DESIGN.md](docs/FRONTEND_DESIGN.md) /
[IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)。**迷ったら設計書が正**。

## これは何か

対談動画から文字起こし・話者分離・字幕生成を行い、切り抜き動画を作るローカルアプリ。
バックエンド(Python/FastAPI)は実装済み、フロント(React)はこれから。

## よく使うコマンド

```bash
./dev.sh              # バックエンド(8000)+フロント(5173)を起動
./dev.sh check        # コミット前の全チェック(pytest + typecheck + lint + vitest + build)
./dev.sh e2e          # E2E(FakeLLM・一時DBなのでGPUもOllamaも不要)

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

## 設計上の重要な決定(変えるときは相談)

- **ASRエンジンはGPUで自動選択(`asr_engine=auto`)。** CUDA→faster-whisper /
  ROCm→whisper.cpp(ビルド済みなら。無ければ公式Whisper)/ GPUなし→faster-whisper CPU。
  CTranslate2はCUDA専用ビルドなのでROCmでは使えない。モデルは large-v3 が既定
  (精度優先・単語タイムスタンプ必須。BACKEND_DESIGN.md)。
  transformers版も選べるが**単語確率とinitial_promptが取れない**ので既定にしない。
- **whisper.cppは `--output-json-full` で呼ぶ(`-ml` を付けない)。**
  句読点・トークンのタイムスタンプ・確率が一度に取れる。`-ml` を付けると
  句読点が落ちる(実測)。セグメント分割は `words_to_segments` で自前に行う。
- **torchはdependency-groupsで切替。** 既定は rocm(RX 7900系)。NVIDIA機は
  `WL_TORCH_GROUP=cu128 ./dev.sh sync`。依存バージョンは固定
  (torch 2.8 / pyannote 3.x / huggingface_hub 0.x / TypeScript 5.9)。上げない。
- **Blackwell GPUでは compute_type="float16" 固定。** int8はクラッシュする(CPUのint8は安全)。
- **設定は3層(グローバル→プロジェクト→クリップ)。** ジョブ・APIは
  `resolve_settings()`(backend/core/project_settings.py)経由で読む。
  ジョブ層でグローバルsettingsを直接importしない(テストで担保)。
- **字幕のpx値は1920×1080基準で保存し、出力解像度へ比率換算する。**
  フォント・左右余白=幅比率、上下余白=高さ比率(subtitle.scaled_style)。
  フロントのプレビューも同じ規則(cqw/cqh)で描く。
- **LLMは提案するだけ、適用は機械ガードを通ったものだけ。**
  `pronoun.validate_edit()` が削除のみ・既出重複・慣用表現などを弾く。この構造を壊さない。
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
  e2e/        Playwright
tests/        pytest(golden/ に移植前の出力を保存し回帰検証)
```

## 日本語UI・日本語コード

- コメント・コミットメッセージ・UI文言は日本語。
- テストケース名も日本語で書いてよい(`test_〜` の中身は日本語文字列でOK)。
- 相槌・フィラー・指示語の判定は日本語特有なので、テストケースを削らない・短縮しない
  (短縮すると意図が変わる。`tests/test_m1_pipeline.py` のコメント参照)。
