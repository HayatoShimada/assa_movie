# 実装計画

[DESIGN.md](DESIGN.md) / [BACKEND_DESIGN.md](BACKEND_DESIGN.md) / [FRONTEND_DESIGN.md](FRONTEND_DESIGN.md) を実装するための計画。
**各タスクは小さく・受け入れ基準付き・検証コマンド付き**で定義し、設計判断を実装時に持ち越さない。

## 進捗(2026-08-07時点)

| M | 状態 | 備考 |
|---|---|---|
| M0 足場 | **完了** | FastAPI起動・SQLite 12テーブル・設定 |
| M1 移植 | **完了** | 移植前goldenとbyte一致を確認(`pytest --run-gpu`で常時検証) |
| M2 ジョブ基盤+API | **完了** | 実動画でcurl E2E確認済み(docs/verify_m2.md) |
| M3 エンジン選択 | **完了** | large-v3既定 / turbo切替 + 設定API |
| M4 指示語置換+HITL | **完了** | FakeLLMで学習ループ検証・質問機能・Gemini API対応含む |
| M5 フロント骨格 | **完了** | ホーム/エディタ/設定タブ・E2E 8件。実Geminiでの指示語解決も確認済み |
| M6 レビューUI+対話 | **完了** | レビュー/質問/アシストのUI+E2E。実Ollama×雑談編でチューニング済み |
| M7 字幕整形・書き出し | **完了** | 禁則処理・ASS焼き込み・フィラー2段判定・採用ジャッジ・概要注入。実書き出し確認済み |
| M8 アテンション+クリップ | **完了** | 候補生成・マウス編集・ジェットカット・中抜き書き出し。実データ検証済み |

| M9 frontend依存修正 | **完了** | jsdom 29固定・engines・npm audit 0件(js-yaml override) |
| M10 ROCm移行 | **完了** | torchをdependency-groups(rocm/cu128)で切替。transformers版Whisperエンジン追加、デバイス自動検出、pyannote CPUフォールバック |
| M11 エンコーダ自動検出 | **完了** | nvenc→vaapi→libx264。ffmpeg不在は日本語エラーで事前通知 |
| M12 プロジェクト設定 | **完了** | 全設定のプロジェクト単位化(差分JSON)・グローバル設定のDB永続化・削除API。ジョブ層はresolve_settings経由に統一 |
| M13 字幕スタイル | **完了** | フォント/文字色/背景ボックス選択。位置・サイズは出力解像度比率で自動スケール(1920×1080では従来と厳密一致) |
| M14 向き変換 | **完了** | 縦→縦/横→縦/横→横/縦→横。crop(位置調整可)/blur_pad/face(1人=追従・2人=上下分割、OpenCV Haar)。クリップ単位上書き |
| M15 フロント | **完了** | テンプレート4択の作成フォーム・プロジェクト設定編集(既定に戻す)・削除UI・クリップ変換UI・縦プレビュー。E2E 25件 |
| M16 環境スキャン | **完了** | 起動時スキャン(GPU/VRAM/エンコーダ/Ollama)・GET /api/environment・VRAM割当設定(torch系に適用)・収まる最良のASR/LLM推奨とワンクリック適用 |

**全マイルストーン完了(2026-08-07)。** テスト: backend 351件 / frontend unit 28件 / E2E 25件。

未実装として残っているもの(README「既知の制限」参照):
- 顔検出レイアウトの動的追従(現状は静的クロップ)
- 複数クリップの一括書き出しUI
- whisper.cpp / Windows(Phase 3)

## 実装者(AI/人間)への共通ルール

1. **設計書が正** — 迷ったら設計書の該当節に従う。設計書にない判断が必要になったら、実装せずTODOコメントと質問を残す
2. **マイルストーン単位でコミット** — 各Mの受け入れ基準を全て満たしてから次へ。飛ばさない
3. **テストファースト** — 各タスクの「テスト」列を先に書き、失敗を確認してから実装する
4. **既存を壊さない** — `transcribe.py` / `resolve_pronouns.py` は各Mの完了時点で従来どおり動くこと(回帰確認: `uv run python transcribe.py <smoke.wav> ja`)
5. **依存バージョンを変えない** — pyproject.tomlのtorch 2.8系 / pyannote 3.x / huggingface_hub 0.x 固定は互換性検証済み。変更禁止(理由はDESIGN.md「制約・技術メモ」)
6. **スコープ外のことをしない** — 各タスクの「やらないこと」を守る。リファクタ衝動は抑える

## リポジトリ構成(monorepo)

```
whisper-local/
├── transcribe.py, resolve_pronouns.py   # 既存CLI(M1以降は内部でbackendモジュールを呼ぶ薄いラッパ)
├── backend/                             # BACKEND_DESIGN.md のツリーどおり
├── frontend/                            # FRONTEND_DESIGN.md のツリーどおり
├── tests/                               # pytest(backend用)
└── pyproject.toml                       # 既存に fastapi 等を追記(バージョン固定に注意)
```

---

## M0: 足場(0.5日規模)

| # | タスク | 成果物 | テスト/検証 |
|---|---|---|---|
| 0-1 | pyproject.tomlに `fastapi`, `uvicorn`, `pydantic-settings`, `sse-starlette`, `pytest`, `httpx` 追加 | 依存追加のみ | `uv sync` 成功、`uv run python transcribe.py` が引き続き動く |
| 0-2 | `backend/app.py`: FastAPI起動 + `GET /api/health` → `{"status":"ok"}` | app.py | `uv run uvicorn backend.app:app` → curl で200 |
| 0-3 | `backend/models/schema.py`: BACKEND_DESIGN.md「データモデル」のテーブルをそのままSQLite DDL化 + 起動時 `CREATE TABLE IF NOT EXISTS` | schema.py | pytest: 全テーブルが作成される・二重起動でもエラーなし |
| 0-4 | `backend/core/config.py`: pydantic-settings。設定項目はBACKEND_DESIGN.mdの設定タブ項目を全列挙(既定値も設計書どおり) | config.py | pytest: 環境変数で上書きできる |

**受け入れ基準**: `uv run uvicorn backend.app:app` が起動し、`whisper.db` が生成され、`uv run pytest` が全て緑。

## M1: 現行ロジックのモジュール化移植(2日規模)

**方針**: 動作を1bitも変えない移植。転記元の行範囲を明記する。

| # | タスク | 転記元 | テスト/検証 |
|---|---|---|---|
| 1-1 | `backend/pipeline/audio.py`: `decode(path) -> np.ndarray`(16kHz mono) | transcribe.py の decode_audio 呼び出し部 | pytest: smoke_test.wav をデコードして長さ・dtype一致 |
| 1-2 | `backend/pipeline/aizuchi.py`: `is_aizuchi(text, duration)` とパターン定数 | transcribe.py の該当関数 | 既存の単体テストケース11件をpytest化して全通過 |
| 1-3 | `backend/engines/asr/base.py`: `Segment`/`Word` dataclassと `ASREngine` Protocol(BACKEND_DESIGN.md「ASRエンジン抽象化」の定義をそのまま) | 設計書 | mypyが通る |
| 1-4 | `backend/engines/asr/fasterwhisper.py`: 現行の文字起こしを `ASREngine` 実装に | transcribe.py | smoke_test.wav で従来出力とセグメント数・テキスト完全一致 |
| 1-5 | `backend/engines/diarize/pyannote.py`: 話者分離+ピッチ話者名判定(`run_diarization`, `estimate_pitch`, `build_label_map`, `assign_speaker`) | transcribe.py | pytest(モック turns でピッチ判定ロジック検証)+ smoke_test.wav 実行で従来と同じ話者割り当て |
| 1-6 | `backend/pipeline/subtitle.py`: SRT/TXT書き出し(現行フォーマットの移植のみ。禁則はM7) | transcribe.py | golden test: smoke_test.wav の出力が現行スクリプトの出力とbyte一致 |
| 1-7 | `transcribe.py` を上記モジュール呼び出しの薄いラッパに書き換え | — | `uv run python transcribe.py smoke.wav ja` の出力が移植前とbyte一致 |

**受け入れ基準**: smoke_test.wav のgolden出力(移植前に生成してtests/golden/に保存)と完全一致。

## M2: ジョブ基盤 + メディア/セグメントAPI(2日規模)

| # | タスク | 内容 | テスト/検証 |
|---|---|---|---|
| 2-1 | `backend/jobs/queue.py` | jobsテーブル + 単一ワーカースレッド。ジョブは直列実行。関数 `enqueue(media_id, type, params) -> job_id` | pytest: ダミージョブが順番に実行され進捗が更新される |
| 2-2 | `backend/jobs/progress.py` | `GET /api/jobs/{id}/events`(SSE)。進捗はDBポーリング(1秒)で配信 | httpxでSSE受信テスト |
| 2-3 | media API | `POST /api/projects` `POST /api/projects/{id}/media`(パス登録・ffprobeでduration取得) | pytest |
| 2-4 | transcribeジョブ | M1のモジュールを繋ぎ、結果をsegmentsテーブルへ保存(original_text=text で初期化) | 雑談編.mov で実行し、セグメント数がDBに550件入る |
| 2-5 | segments API | `GET /api/media/{id}/segments` `PATCH /api/segments/{id}`(text/speaker変更、edited_by_user=1) | pytest + curl |

**受け入れ基準**: curlのみで「動画登録→文字起こしジョブ→SSEで進捗→セグメント取得→1件修正」が通る手順書(`docs/verify_m2.md`)どおりに動く。

## M3: エンジン選択機構(0.5日規模)

**前提(検証・決定済み)**: 2026-08-07のベンチ(BACKEND_DESIGN.md「検証済み」表)とユーザー決定
(精度優先・単語TS必須)により、**既定=large-v3、速度モード=large-v3-turbo** に確定。
kotoba-whisperは単語TS不可のため不採用(エンジン追加タスクは無し)。

| # | タスク | 内容 | テスト/検証 |
|---|---|---|---|
| 3-1 | モデル選択 | config `asr_model: "large-v3"(既定) \| "large-v3-turbo"` をfasterwhisperエンジンに配線 | pytest: 設定でモデルIDが切り替わる |
| 3-2 | 遅延ロード+`unload()` | エンジンの遅延ロードとVRAM解放 | pytest: `torch.cuda.memory_allocated` 減少確認 |
| 3-3 | UI表示用の注意書き | turbo選択時「発話が標準語化される場合があります」を設定APIのメタ情報に含める | pytest |

## M4: 指示語置換サービス + Human-in-the-loop(3日規模)

| # | タスク | 内容 | テスト/検証 |
|---|---|---|---|
| 4-1 | `backend/engines/llm/base.py` | `LLMClient` Protocol: `resolve(chunk, context, instructions, feedback) -> list[EditProposal]`。**テスト用 `FakeLLMClient`(固定応答)を同時に作る** | — |
| 4-2 | `backend/engines/llm/ollama.py` | resolve_pronouns.py の呼び出し部を移植(スキーマ・リトライ含む)。確信度フィールド追加(プロンプトで `confidence: "auto"\|"review"` を要求) | FakeLLM でパイプライン全体、実Ollamaはスモークのみ |
| 4-3 | プロンプト合成 | BACKEND_DESIGN.md「LLM協調」の合成順(レベル→用語集→指示→feedback few-shot→チャンク)を `build_prompt()` 純関数に | pytest: 合成順・件数上限のテーブルテスト |
| 4-4 | resolveジョブ | 編集検証(original実在等、resolve_pronouns.pyのルール)→ editsテーブルへ proposed で保存 → autoは設定次第で即適用 | FakeLLMで: 提案保存・auto適用・検証スキップの3ケース |
| 4-5 | レビューAPI | accept(修正付き可)/reject(→feedback記録)/revert + `GET /edits?status=` | pytest |
| 4-6 | instructions/glossary CRUD + 用語集のASR連携(initial_prompt) | 設計書どおり | pytest |
| 4-7 | 範囲再実行 | scope=all/segment_ids/unresolved。承認済み編集は保持 | pytest: 再実行で適用済みが消えないこと |
| 4-8 | `resolve_pronouns.py` を薄いラッパ化 | — | 従来CLIの出力形式(置換済/ログ)が維持される |
| 4-9 | 質問機能 | questionsテーブル + extract_termsジョブ(固有名詞スキャン→表記ゆれ/低信頼を質問化)+ answer API(用語集登録+一括修正) | FakeLLMで: 質問生成→回答→全出現箇所修正→用語集登録の一連 |

**受け入れ基準**: FakeLLMによる統合テストで「提案→却下→feedbackがfew-shotに載って再実行」のループが自動テストで通る。

## M5: フロントエンド骨格(3日規模)

| # | タスク | 内容 | 検証 |
|---|---|---|---|
| 5-1 | `frontend/` 初期化 | Vite+React+TS+Tailwind+shadcn/ui。`npm run build` をCI相当に | build成功 |
| 5-2 | API型生成 | FastAPIのopenapi.json → `openapi-typescript`。`npm run gen:api` スクリプト化 | 型チェック通過 |
| 5-3 | ホーム画面 | プロジェクト/メディア一覧・登録・ジョブ進捗バー(SSE) | 手動: 雑談編を登録し文字起こし完了まで見える |
| 5-4 | エディタ骨格 | video要素+セグメントリスト(TanStack Virtual)+クリックシーク+再生追従ハイライト | 手動確認チェックリスト(`docs/verify_m5.md`) |
| 5-5 | 設定タブ | config APIと双方向バインド | 手動 |

## M6: 置換レビューUI + 対話アシスト(2日規模)

- 6-1: 置換レビュータブ(FRONTEND_DESIGN.mdの仕様どおり: バッジ・3ボタン・j/k/a/xショートカット・再実行バー)
- 6-2: トランスクリプトの置換箇所下線+原文ツールチップ
- 6-3: `POST /api/segments/{id}/assist`(バックエンド)+ ミニチャットUI(フロント)。指示昇格ダイアログ
- 6-4: 質問キューUI(カード・候補ボタン・ジャンプリンク・未回答バッジ)
- 検証: FakeLLMを使ったPlaywright E2E(承認・却下・再実行の3シナリオ)

## M7: 字幕整形・スタイル・書き出し(3日規模)

- 7-1: `subtitle.py` に折返し・禁則処理(設計書の規則をテーブル駆動テストで25ケース以上。**純関数にすること**)
- 7-2: ASS生成(スタイル: フォント・色・位置・話者別色)
- 7-3: `pipeline/export.py`: ffmpeg切り出し+libass焼き込み+NVENC。単一クリップの書き出しAPI
- 7-4: フロント: 字幕スタイル設定UI+CSSオーバーレイプレビュー(7-1と同一テストケースをTS側でも通す)
- 7-5: フィラー排除(BACKEND_DESIGN.md「フィラー排除」)。安全群は正規表現、文脈依存群はM4のLLM編集リスト機構を再利用(kind='filler')。FakeLLMでテスト
- 7-6: 字幕採用ジャッジ(BACKEND_DESIGN.md「字幕採用ジャッジ」)。機械シグナル(asr_confidence・発話速度)は純関数でテーブルテスト、LLM評価はFakeLLM。フロントは採用バッジ+切替
- 7-7: 指示語置換の表現形式(注釈/置換/補完)の適用関数。編集データの `referent` から3形式を生成する純関数+テーブルテスト
- 検証: 雑談編の任意60秒を書き出し、字幕付きmp4が再生できる。選択字幕モードで採用率が設定に従う

## M8: アテンション + クリップ編集 + 一括書き出し(5日規模・Phase 2)

- 8-1: `pipeline/attention.py` スコアリング(設計書の入力素性。LLM評価はFakeLLMでテスト)
- 8-2: clips/clip_cuts/templates API + ジェットカット提案(無音検出: ffmpeg silencedetect)
- 8-3: クリップ文脈の指示語自己完結化(`POST /clips/{id}/resolve`。M4の機構を再利用)
- 8-4: フロント: 候補タブ→クリップ編集モード(トリム・スナップ・中抜きON/OFF・尺カウンタ)
- 8-5: フックテキスト生成・メタ生成・書き出しキュー・テンプレート
- 8-6: **[要検証]** 縦型レイアウト(顔検出追従は8-6完了後に別途判断)

---

## タスク粒度の原則(実装AI向け)

- 1タスク = 1ファイル前後、1コミット。100行超の新規ファイルは分割を検討
- 「テスト/検証」列が曖昧なまま実装を始めない
- UIの見た目はshadcn/uiの既定スタイルで良い(デザイン調整は全機能完成後)
- **[要検証]** マークのタスクは結果レポートを出すところまでが仕事。判断はしない

## マイルストーン依存関係

```
M0 → M1 → M2 → M3(独立可) 
           └→ M4 → M6
           └→ M5 → M6, M7 → M8
```

M3とM4/M5は並行可能。M8はM4/M7完了後。
