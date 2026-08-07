# バックエンド詳細設計(日本語特化)

[DESIGN.md](DESIGN.md) のバックエンド部分の詳細設計。ASRは **kotoba-whisper** を主軸にした日本語特化仕様。

## 技術スタック

| 層 | 採用 | 理由 |
|---|---|---|
| Webフレームワーク | FastAPI + uvicorn | 非同期・SSE対応・pydanticとの親和性 |
| ASR(主) | kotoba-whisper v2.2 (HF Transformers) | 日本語特化蒸留で large-v3 比 約6.3倍速・同等精度。PyTorchなのでCUDA/ROCm両対応。句読点付与(punctuators)同梱 |
| ASR(代替) | faster-whisper large-v3 (現行) | NVIDIA環境での実績あり。多言語対応が必要な場合の切替先 |
| ASR(フォールバック) | whisper.cpp | CPU・省VRAM・Vulkan環境用(Phase 3) |
| 話者分離 | pyannote.audio 3.1 + ピッチ話者名判定(現行実装を移植) | 実データ検証済み。kotoba-whisper v2.2同梱のdiarizersは代替オプションとして保持 |
| 指示語解決LLM | Ollama (qwen3:32b) / Claude API 切替 | ローカル/クラウド選択可能の要件 |
| ジョブ管理 | SQLite + 単一ワーカー | GPUジョブは直列実行が前提なので分散キュー不要 |
| 動画処理 | ffmpeg (デコード・切り出し・NVENC書き出し・libass字幕焼き込み) | |

## 全体構成

```
backend/
├── app.py                  # FastAPI起動・静的ファイル配信
├── api/
│   ├── projects.py         # プロジェクト・メディア登録
│   ├── jobs.py             # ジョブ投入・進捗SSE
│   ├── transcripts.py      # セグメントCRUD(UI編集用)
│   └── clips.py            # 切り抜き候補・書き出し
├── core/
│   └── config.py           # pydantic-settings(UI設定と1対1対応)
├── jobs/
│   ├── queue.py            # SQLiteジョブテーブル + ワーカースレッド
│   └── progress.py         # 進捗イベント発行(SSE)
├── engines/
│   ├── asr/
│   │   ├── base.py         # ASREngine抽象クラス
│   │   ├── kotoba.py       # kotoba-whisper v2.2
│   │   └── fasterwhisper.py# 現行transcribe.pyの移植
│   ├── diarize/
│   │   └── pyannote.py     # 現行の話者分離+ピッチ判定を移植
│   └── llm/
│       ├── base.py         # 指示語解決クライアント抽象
│       ├── ollama.py       # 現行resolve_pronouns.pyの移植
│       └── anthropic.py    # クラウドAPI版
├── pipeline/
│   ├── audio.py            # PyAVデコード(16kHz mono)・silero-VAD
│   ├── aizuchi.py          # 相槌フィルタ(現行移植・パターン設定可)
│   ├── pronoun.py          # 指示語置換の適用・検証・ログ(3段階)
│   ├── subtitle.py         # 日本語整形・禁則処理・SRT/ASS生成
│   ├── attention.py        # 切り抜き候補スコアリング(Phase 2)
│   └── export.py           # ffmpeg切り出し・字幕焼き込み
└── models/
    └── schema.py           # pydanticモデル + SQLiteテーブル定義
```

## ASRエンジン抽象化

```python
@dataclass
class Word:
    start: float; end: float; text: str

@dataclass
class Segment:
    start: float; end: float; text: str
    words: list[Word] | None      # エンジンにより無い場合がある(下記注意)
    speaker: str | None = None

class ASREngine(Protocol):
    name: str
    def transcribe(self, audio: np.ndarray, language: str,
                   progress: Callable[[float], None]) -> list[Segment]: ...
    def unload(self) -> None      # VRAM解放(ステージ直列実行のため)
```

- 音声デコードはエンジン外(`pipeline/audio.py`)で一元化。全エンジンに同じ16kHz mono配列を渡す(現行transcribe.pyと同じPyAV方式。.mov等コンテナ差異をエンジンから隠蔽)
- **要検証**: kotoba-whisperは蒸留モデルのため単語タイムスタンプの精度が本家Whisperより弱い可能性がある。実装時に既存2動画で検証し、不足なら「セグメント時刻はkotoba、単語時刻はセグメント内文字数比例配分」で近似する
- エンジンは遅延ロード+ステージ終了時に `unload()`。VRAM 8GB級のGPUでも動くよう、ASR→話者分離→LLMは直列実行が既定

## 処理パイプライン

```
メディア登録
  → [job:transcribe] デコード → VAD → ASR(kotoba) → 句読点付与
       → 話者分離(pyannote) → ピッチで話者名割り当て → 相槌フラグ付け
  → [job:resolve]   指示語置換(3段階) ※有効時のみ
  → [job:attention] 切り抜き候補スコアリング(Phase 2)
  → [job:export]    範囲確定 → ffmpeg切り出し → 字幕焼き込み → NVENC書き出し
```

- 各ジョブは独立に再実行可能。上流をやり直しても下流の手動編集を極力保持する(セグメントIDで突合)
- 進捗は `progress(0.0〜1.0)` コールバック → SSEでUIへ

## 日本語特化仕様

### 相槌・フィラー(現行実装を設定化)
- 相槌パターン(うん・はい・なるほど等)+ 最大2秒 → `is_aizuchi` フラグ。UI切替: 除外/グレー表示/残す
- フィラー「あの」「その」「なんか」は**削除しない**(発話の個性を保つ)。ただし字幕モードでは行頭フィラーの除去をオプション提供

### 指示語置換の3段階
| 段階 | 対象 | プロンプト方針 |
|---|---|---|
| 弱 | これ・それ・あれ 単体のみ | 「一意に明確な場合のみ」+ 置換上限20文字 |
| 中(既定) | + この/その/あの+名詞 | 現行resolve_pronouns.py相当。上限40文字 |
| 強 | + こういう/そういう/ああいう | 「文脈から合理的に推定できれば置換」。上限60文字 |
- 全段階共通: フィラー保護・編集リスト方式(original実在検証)・置換ログ必須。ログはUIで差分表示し、1件ずつ取り消し可能にする

### 字幕整形(subtitle.py)
- 1行の最大文字数: 既定15文字(UIで10〜20可変)、最大2行。超過時はセグメントを句読点・単語境界で分割
- 禁則処理: 行頭に「、。」」!?ゃゅょっー」等を置かない、行末に「「(」を置かない
- 正規化: NFKC + 数字は文脈で半角/全角選択。話者ごとに色/位置スタイル(ASS)。SRTは互換用に同時出力
- 表示時間: 最短1.0秒・文字数×0.15秒を下限に自動延長(読み切れる速度を保証)

## LLM協調ワークフロー(Human-in-the-loop)

LLM機能(指示語置換・将来のアテンション)は完全自動にせず、**ユーザーの指示とフィードバックを蓄積して反復的に精度を上げる**構造にする。

### 1. ユーザー指示の注入(実行前)
LLMへのプロンプトは毎回、次の順で合成する:

```
基本システムプロンプト(置換レベル 弱/中/強)
+ プロジェクト用語集(人名・製品名・イベント名と説明)
+ プロジェクト/メディア単位のカスタム指示
    例:「この対談での『あれ』は基本的にAIハッカソンを指す」
        「『ゆいちゃん』ははやまるの妻。敬称を付けない」
+ 過去のフィードバック(却下・修正された編集の実例を few-shot として最大N件)
+ 処理対象チャンク
```

- **用語集はASRにも共用する**: Whisper系の `initial_prompt` / ホットワードに用語を渡し、
  固有名詞の文字起こし精度も同じデータで改善する(一度の入力が全工程に効く)
- カスタム指示は有効/無効を個別に切替可能(効果の切り分けができるように)

### 2. 提案 → レビュー → 適用のサイクル(実行後)
- 置換ジョブの結果は即適用ではなく **提案(proposed)** として保存し、LLMの確信度で二分する:
  - `auto`: 確信度が高い提案。設定「自動適用」ONなら即適用(現行スクリプト相当の動作)
  - `review`: 確信度が低い提案。必ずユーザーレビュー待ちにする
- ユーザーの操作: 承認 / 却下 / 置換内容を手で修正して承認
- **却下・修正は `feedback` として記録され、次回実行時に few-shot 例として自動注入される**
  → 同じ誤りを繰り返さない。これが「繰り返し修正しながら精度を上げる」の中核
- 再実行は範囲指定可能(全体 / 選択セグメントのみ / 未解決のみ)。承認済みの編集は再実行でも保持する

### 3. 対話アシスト(ピンポイント修正)
- セグメントを選択して自然言語で指示できるチャットAPIを設ける
  例: 「この『それ』は前の話の文字起こしアプリのこと」→ LLMが該当編集の提案を返す → 承認で適用
- 対話の結論はカスタム指示 or 用語集への昇格を提案する
  (「今後もこの解釈を使いますか?」→ YESで恒久ルール化)

### 4. 対話を挟む場所(プロセス設計)
```
文字起こし → [確認1] 話者名・用語集の確認(誤字の多い固有名詞を提示)
          → 指示語置換(提案生成) → [確認2] レビューUIで承認/却下/修正
          → (フィードバック蓄積) → 必要なら範囲再実行 → 確定
          → アテンション候補 → [確認3] 候補の採否・範囲調整(Phase 2)
```
- 各確認ステップはスキップ可能(全自動モード)。既定は「auto適用+reviewのみ確認」の中間

## データモデル(SQLite)

```
projects(id, name, created_at)
media(id, project_id, path, duration, status)
segments(id, media_id, idx, start, end, text, original_text,
         speaker, is_aizuchi, edited_by_user)
edits(id, media_id, segment_id, kind='pronoun', original, replacement,
      status='proposed|applied|rejected|reverted',
      confidence='auto|review', created_by='llm|user')
llm_instructions(id, project_id, media_id?, scope='pronoun|asr|attention|all',
                 text, enabled, created_at)
glossary(id, project_id, term, reading?, description)   -- ASRのinitial_promptにも共用
feedback(id, media_id, edit_id?, kind='rejection|correction|instruction',
         before, after?, note?, created_at)             -- 次回実行のfew-shot例
clips(id, media_id, start, end, title, hook_text, score, score_reasons_json,
      layout='landscape|vertical_single|vertical_stack',
      template_id?, target_duration?, status)
clip_cuts(id, clip_id, start, end, source='silence|aizuchi|manual', active)
      -- クリップ内の中抜き区間(ジェットカット)。activeをOFFにすると復活
templates(id, name, subtitle_style_json, layout, target_duration)
jobs(id, media_id, type, params_json, status, progress, error, created_at)
```

- `original_text` を必ず保持(指示語置換・ユーザー編集後も原文に戻せる)
- 指示語置換は `edits` に記録 → 置換ログUIと取り消しがそのまま実現できる

## API(抜粋)

```
POST /api/projects                        プロジェクト作成
POST /api/projects/{id}/media             動画登録(パス指定)
POST /api/media/{id}/jobs                 {type: transcribe|resolve|export, params}
GET  /api/jobs/{id}/events                SSE進捗
GET  /api/media/{id}/segments             セグメント一覧(UI表示・編集)
PATCH /api/segments/{id}                  テキスト・話者の手動修正
GET  /api/media/{id}/edits?status=        置換の提案/適用済み一覧
POST /api/edits/{id}/accept               提案の承認(修正付き承認は body で replacement 上書き)
POST /api/edits/{id}/reject               提案の却下(理由付き → feedbackに記録)
POST /api/edits/{id}/revert               適用済み置換の取り消し
CRUD /api/projects/{id}/instructions      カスタム指示の管理
CRUD /api/projects/{id}/glossary          用語集の管理
POST /api/media/{id}/jobs                 type=resolve, params={level, scope: all|segment_ids|unresolved}
POST /api/segments/{id}/assist            対話アシスト {message} → 編集提案を返す(SSE)
POST /api/media/{id}/clips/suggest        切り抜き候補生成 {target_duration?, theme?}
POST /api/clips/{id}/jetcut               中抜き提案(無音・相槌・脱線)を生成
POST /api/clips/{id}/resolve              クリップ文脈での指示語再解決(自己完結化)
POST /api/clips/{id}/meta                 タイトル・概要欄・ハッシュタグ生成
POST /api/export/batch                    複数クリップの一括書き出し {template_id}
```

## クリップ生成・再調整(動画制作者ワークフロー)

「候補を選ぶ → 尺に収める → 見栄えを整える → 一括書き出し」を最短距離にする。

### 候補生成(attention.py)
- スコアリング入力: 話題の自己完結性(LLM評価)・盛り上がり(音量/発話密度/笑い)・話者交替パターン・フック強度(冒頭発言の引き)
- 候補には `score_reasons`(「完結した話題」「笑いあり」等のタグ)を必ず付け、UIで根拠を表示
- `target_duration`(15/30/60/90秒)を指定すると、その尺に収まる区間を優先して提案

### クリップ単位の再調整
- **トリム**: 開始/終了は「セグメント境界・無音・話者交替点」にスナップ(文の途中で切れない保証)。
  スナップ解除でフレーム単位調整も可
- **中抜き(ジェットカット)**: 無音(閾値・最小長設定可)と相槌セグメントを `clip_cuts` として自動提案。
  1件ずつON/OFF可能。テンポ重視の切り抜きの尺圧縮を自動化する
- **指示語の自己完結化**: 切り抜きは前文脈が消えるため、クリップ先頭付近の「それ」「あの話」が
  視聴者に通じなくなる。`POST /clips/{id}/resolve` で**元動画の全文脈を参照しつつ
  クリップ内だけで意味が通る置換**を再実行する(このアプリ固有の強み)
- **フックテキスト**: クリップ冒頭に載せる一言(釣りテロップ)をLLMが3案生成、ユーザーが選択・編集

### 見栄え・書き出し
- 縦型(9:16)レイアウト: `vertical_single`(顔中心の自動クロップ・顔検出で話者に追従)/
  `vertical_stack`(2人対談の上下分割)。顔検出はmediapipe等、Phase 2後半
- テンプレート: 字幕スタイル+レイアウト+目標尺のプリセット。候補承認→テンプレ適用→
  `POST /api/export/batch` で複数クリップをNVENCで連続書き出し
- メタ生成: クリップの文字起こしからタイトル・概要欄・ハッシュタグを自動生成(用語集・カスタム指示を共用)

## 実装フェーズ

1. **Phase 1**: 現行3スクリプトのモジュール化移植 + kotoba-whisperエンジン追加 + ジョブ基盤 + セグメントAPI(UIなしでcurl検証可能な状態)
2. **Phase 2**: アテンション機能(発話密度・話者交替・LLM話題評価によるスコアリング)+ 書き出し
3. **Phase 3**: whisper.cpp・ROCm実機検証・Windows対応・クラウドASR

## 検証方針

- 既存2動画(雑談編・aiイベント)を回帰テストデータとする。kotoba-whisper移行時は現行large-v3出力とのCER差分・処理時間・単語タイムスタンプ精度を比較してから既定エンジンを切り替える
- 相槌・指示語・字幕整形は現行スクリプトの出力と一致することをユニットテストで担保してから移植完了とする
