# バックエンド詳細設計(日本語特化)

[DESIGN.md](DESIGN.md) のバックエンド部分の詳細設計。日本語特化仕様。
ASRは **faster-whisper large-v3 を既定**とする(2026-08-07決定: 精度優先・単語タイムスタンプ必須の要件による。実測比較は「検証済み」表を参照)。

## 技術スタック

| 層 | 採用 | 理由 |
|---|---|---|
| Webフレームワーク | FastAPI + uvicorn | 非同期・SSE対応・pydanticとの親和性 |
| ASR(既定) | faster-whisper large-v3 (現行) | 実測で品質最良(方言保持・取りこぼし最少)+単語タイムスタンプ健全。RTF25倍で75分動画も約3分 |
| ASR(速度モード) | faster-whisper large-v3-turbo | 単語TS付きでRTF111倍。発話を標準語化する癖があるため既定にはしない |
| ASR(不採用) | kotoba-whisper v2.0/v2.2 | 単語タイムスタンプ取得不可のため要件(単語TS必須)を満たさない。CT2変換版はセグフォルト |
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
│   │   └── fasterwhisper.py# 現行transcribe.pyの移植(large-v3既定/turboは設定切替)
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
- **検証済み(2026-08-07、雑談編300秒・RTX PRO 6000で実測)**:

| モデル | 処理時間 | RTF | 単語TS | 所見 |
|---|---|---|---|---|
| faster-whisper large-v3(現行) | 12.2秒 | 25倍 | ○ | 方言保持(「関わらんとって」)・冒頭の断片も拾う。品質最良 |
| faster-whisper large-v3-turbo | 2.7秒 | 111倍 | ○ | 4.5倍高速で単語TS健全。ただし発話を標準語化する傾向(「関わらないとって」) |
| kotoba-whisper v2.0(HF) | 2.4秒 | 124倍 | **×** | 最速・方言保持。単語TSはIndexErrorで取得不可(蒸留モデルの制約が実証された) |
| kotoba-whisper v2.0-faster(CT2) | — | — | — | CTranslate2現行版でセグフォルト。**不採用確定** |

  - 依存関係はtransformers 4.57.6が現行固定(torch 2.8/pyannote 3.x/hf_hub 0.36)と共存可能なことを隔離環境で確認済み
  - kotoba採用時の単語時刻は「セグメント内文字数比例配分」で近似する(チャンク平均3.4秒なので字幕表示には十分、スナップ・ジェットカットの精度はturbo/v3に劣る)
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

### 相槌除外(セグメント単位・現行実装を設定化)
- 相槌パターン(うん・はい・なるほど等)+ 最大2秒 → `is_aizuchi` フラグ。UI切替: 除外/グレー表示/残す

### フィラー排除(発話内の語単位・有効/無効切替可)
相槌(独立したセグメント)とフィラー(発話の中の言い淀み語)は別機能として扱う。

- 対象語を**安全度で2群に分ける**:
  - 安全群(常に機械削除可): 「あー」「えー」「えっと」「あのー」「まあその、」等の間投詞。正規表現+位置ヒューリスティックで削除
  - 文脈依存群(LLM判定必須): 「なんか」「まあ」「その」「こう」「あ、」— 意味を持つ用法がある
    (例: 「なんかあった?」の なんか は削除不可)。指示語置換と同じ編集リスト方式でLLMに判定させる
- 強度設定: 無効 / 弱(安全群のみ) / 強(文脈依存群もLLM判定で削除)。対象語リストはUIで編集可能
- 非破壊: `edits(kind='filler')` として記録し、レビュー・取り消し・feedback蓄積は指示語置換と同じ機構を共用
- 適用先: 字幕・書き出しテキストのみ。`original_text` は常に原文を保持(発話の個性はデータとして残す)

### 指示語置換(積極性 × 表現形式 の2軸)

**軸1: 積極性(どの指示語を対象にするか)**
| 段階 | 対象 | プロンプト方針 |
|---|---|---|
| 弱 | これ・それ・あれ 単体のみ | 「一意に明確な場合のみ」+ 置換上限20文字 |
| 中(既定) | + この/その/あの+名詞 | 現行resolve_pronouns.py相当。上限40文字 |
| 強 | + こういう/そういう/ああいう | 「文脈から合理的に推定できれば置換」。上限60文字 |

**軸2: 表現形式(どう表示するか)** — 良い字幕は単純置換より「補足」であるという方針
| 形式 | 出力例 | 特徴 |
|---|---|---|
| 注釈(既定) | それ(去年のハッカソン)がすごくて | **発言を一切改変しない**ため最も安全。字幕の標準的な作法。confidence=autoで即適用可 |
| 置換 | 去年のハッカソンがすごくて | 読みやすいが発言の改変になる。現行プロトタイプの動作 |
| 補完 | それ(去年のハッカソン)が(運営も内容も)すごくて | 言い落とされたニュアンスまで括弧で補う意訳寄りの形式。**全件review必須**(自動適用禁止) |

- 同じ編集リスト(original/replacement/参照先)から3形式を生成できるため、LLM呼び出しは1回で
  形式の切替は再実行不要(参照先 `referent` を編集データに持ち、適用時に形式を選ぶ)
- 全段階・全形式共通: フィラー保護・編集リスト方式(original実在検証+削除のみ/既出重複/慣用表現の機械ガード)・
  置換ログ必須。ログはUIで差分表示し、1件ずつ取り消し可能にする
- おすすめモード既定: 積極性=中 × 形式=注釈(補足の恩恵を得つつ発言改変リスクゼロ)

### 字幕採用ジャッジ(選択字幕モード)
全セグメントを字幕にすると画面がうるさい。字幕モードを2種用意する:
- **全文字幕**: 全セグメントを字幕化(バラエティ・切り抜き向け。現行動作)
- **選択字幕(理解補助型)**: 「聞き取りを助ける・理解に必要な文脈」だけを字幕化

選択字幕の採用判定は機械シグナル+LLM評価の合成スコアで行う:
| シグナル | 取得元 | 意味 |
|---|---|---|
| 聞き取りにくさ | ASRの信頼度(avg_logprob)・発話速度(文字数/秒)・音量・話者かぶり | 低信頼=耳で聞き取りづらい可能性 → 字幕が必要 |
| 固有名詞・専門用語 | 用語集とのマッチ+LLM判定 | 初出の固有名詞は字幕で補助 |
| 文脈上の重要度 | LLM評価(話題の転換点・結論・決め台詞) | 理解の骨格になる発言 |

- 判定結果は `segments.subtitle_show('auto_show'|'auto_hide'|'user_show'|'user_hide')` +
  `subtitle_reasons`(根拠タグ)で保存。**ユーザーのワンクリック切替(user_*)が常に優先**され、
  切替はfeedbackとして蓄積 → 再ジャッジ時のfew-shotに使う(Human-in-the-loop共通機構)
- 採用率の目安をスライダーで指定可能(例: 3割だけ字幕化)。スコア上位から採用する

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

### 4. LLMからの質問(逆方向の対話)
ユーザーが指示するだけでなく、**LLMが分からないことをユーザーに質問する**チャネルを持つ。

- **固有名詞の確認(主用途)**: 文字起こし全体をスキャンし、固有名詞候補を抽出。
  次の条件で「質問」を生成する:
  - ASR信頼度が低い、または表記ゆれがある(例: 箱ストア/ハコストア が混在)
  - 音は分かるが漢字表記が確定できない(例: 「はんどうたい」→ 反動体? 半導体?)
  - 実例: 今回の文字起こしでも「反動体(半導体)」「分泌家(文筆家)」等の誤認識が発生しており、
    音的に正しく漢字だけ誤るケースは機械では確定できない
  - 質問形式: 「『反動体』(12回出現)は『半導体』の誤認識と思われます。正式表記を教えてください」
    + 推定候補を選択肢で提示(ワンタップ回答)
- **指示語の質問**: 解決の確信が持てないがユーザーに聞けば分かりそうな場合、editの代わりに
  質問を出せる(「この『あの話』は何を指しますか?」+ 該当箇所へのジャンプリンク)
- 回答の処理: 固有名詞 → 用語集に登録 + 全出現箇所を一括修正(edits kind='term') +
  以後のASR initial_prompt に反映(再文字起こしでも正しくなる)。指示語 → 編集として適用
- 質問はまとめて表示し、後回し・却下も可能。未回答でもパイプラインは止めない(非ブロッキング)

### 5. 対話を挟む場所(プロセス設計)
```
文字起こし → [確認1] 話者名確認 + LLMからの質問キュー(固有名詞の表記確認)
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
         speaker, is_aizuchi, edited_by_user,
         asr_confidence,                          -- 字幕採用ジャッジの入力
         subtitle_show='auto_show|auto_hide|user_show|user_hide',
         subtitle_reasons_json)
edits(id, media_id, segment_id, kind='pronoun', original, replacement,
      status='proposed|applied|rejected|reverted',
      confidence='auto|review', created_by='llm|user')
llm_instructions(id, project_id, media_id?, scope='pronoun|asr|attention|all',
                 text, enabled, created_at)
glossary(id, project_id, term, reading?, description)   -- ASRのinitial_promptにも共用
feedback(id, media_id, edit_id?, kind='rejection|correction|instruction',
         before, after?, note?, created_at)             -- 次回実行のfew-shot例
questions(id, media_id, kind='term|pronoun', target_json,  -- 対象語/セグメントID
          question_text, candidates_json?,               -- 推定候補(選択肢)
          status='open|answered|dismissed', answer?, created_at)
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
POST /api/media/{id}/jobs                 type=extract_terms(固有名詞スキャン→質問生成)
GET  /api/media/{id}/questions?status=    LLMからの質問一覧
POST /api/questions/{id}/answer           回答 {text} → 用語集登録+一括修正を実行
POST /api/questions/{id}/dismiss          質問の却下
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
