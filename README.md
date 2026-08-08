# Attention Subtitle Separate Application

対談・イベント動画から **文字起こし → 話者分離 → 指示語の解決 → 字幕生成 → 切り抜き動画作成** までを、
すべてローカルGPUで行うアプリケーションです。バージョン **0.4.0**。

<https://github.com/> ※公開リポジトリのURLが決まったらここに記載

## 何ができるか

- **文字起こし**: Whisper large-v3 による高精度な日本語文字起こし。単語タイムスタンプ・単語確率付き
  (GPUに応じて faster-whisper / whisper.cpp / 公式Whisper を自動選択)
- **話者分離**: pyannote.audio + 声の高さによる話者名の自動割り当て(男女2人の対談に最適化)
- **相槌・フィラー処理**: 「うん」「なるほど」等の相槌除外、「あのー」「なんか」等の言い淀みを
  字幕からだけ除去(原文は常に保持)。曖昧なものはAIがユーザーに質問する
- **指示語の解決**: 「それ」「あれ」が指す内容をLLMが補足(`それ(先月のイベント)` 形式)。
  提案はすべて機械検証を通り、レビューUIで承認・却下・修正できる
- **固有名詞の確認**: 誤認識されやすい固有名詞(例: 半導体→反動体)をAIが検出して質問。
  回答で全出現箇所を一括修正+用語集登録
- **字幕**: 日本語の禁則処理付き折返し、話者別カラー、全文字幕/選択字幕モード。
  フォント・文字色・背景ボックスを選択でき、位置・サイズは出力解像度に対する比率で
  自動スケール(縦動画でも見た目の比率が一定)
- **プロジェクトテンプレート**: 作成時に「縦→縦 / 横→縦 / 横→横 / 縦→横」を選択。
  横→縦は 中央クロップ(位置調整可)/ ぼかし背景 / 顔検出(1人=追従クロップ・2人=上下分割)
  の3方式。全設定をプロジェクト単位で上書きでき、未変更の項目は全体設定に追従
- **切り抜き**: LLM+機械特徴(笑い・テンポ・掛け合い)による候補提案、
  マウス操作のトリム、ジェットカット(無音・相槌の中抜き)、タイトル・フック・ハッシュタグ生成
- **書き出し**: ASS字幕焼き込み+ハードウェアエンコード(NVENC / VAAPI を自動検出、無ければlibx264)
- **環境スキャン**: 起動時にGPU・VRAM・エンコーダ・Ollamaを自動検出。設定タブの環境パネルで
  VRAM割当を調整でき、割当に収まる最良のASRモデル・LLMをワンクリックで適用できる

LLMはローカル(Ollama)とクラウド(Gemini API)を切り替え可能。ローカル運用なら
動画・音声データは一切外部に送信されません。

## 動作要件

| 項目 | 要件 |
|---|---|
| OS | Ubuntu 22.04+ (Windowsは未対応・v1.0で対応予定) |
| GPU | NVIDIA GPU(CUDA 12.x)または AMD GPU(ROCm 6.4+。RX 7900系で検証)。VRAM 8GB以上推奨 |
| Python | 3.12(uvが自動で管理) |
| Node.js | 20以上(フロントエンド用) |
| ffmpeg | 必須(動画のデコード・書き出し。`apt install ffmpeg`) |
| [uv](https://docs.astral.sh/uv/) | Pythonパッケージ管理 |
| [Ollama](https://ollama.com/)(任意) | ローカルLLM用。`qwen3:32b` 推奨(VRAM 24GB以上) |

- **注意: Blackwell世代GPU(RTX 50シリーズ / RTX PRO 6000)** では int8 が
  クラッシュするため float16 固定です(設定済み・変更不要)
- Ollamaを使わない場合は Gemini API キーで代替できます(後述)

## セットアップ

```bash
git clone <このリポジトリ> && cd whisper-local

# 1. Python依存(初回は数GBのダウンロード)
#    AMD GPU (ROCm、既定):
./dev.sh sync            # = uv sync(ROCm版PyTorch)
#    NVIDIA GPU (CUDA):
# WL_TORCH_GROUP=cu128 ./dev.sh sync
#    ASRエンジンはGPUに合わせて自動選択される
#    (CUDA→faster-whisper / ROCm→whisper.cppか公式Whisper / GPUなし→CPU)

# 1b. (任意・ROCmのみ)whisper.cppを用意すると文字起こしが約3倍速くなる
#     sudo apt install cmake
#     ./dev.sh whispercpp

# 2. フロントエンド依存
cd frontend && npm install && cd ..

# 3. 話者分離用の HuggingFace トークン(無料)
#    - https://huggingface.co/join でアカウント作成
#    - https://huggingface.co/pyannote/speaker-diarization-3.1 の規約に同意
#    - https://huggingface.co/pyannote/segmentation-3.0 の規約に同意
#    - https://huggingface.co/settings/tokens でトークン発行(Read権限)
echo "hf_あなたのトークン" > hf_token.txt

# 4a. ローカルLLM(推奨: プライバシー重視)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:32b

# 4b. またはクラウドLLM(Gemini API)
#     https://aistudio.google.com/apikey でキーを発行
echo "あなたのAPIキー" > gemini_api_key.txt
```

`hf_token.txt` / `gemini_api_key.txt` は `.gitignore` 済みでコミットされません。

## 起動と使い方

```bash
./dev.sh          # バックエンド(:8000)とフロントエンド(:5173)を起動
```

ブラウザで <http://localhost:5173> を開き:

1. プロジェクトを作成し、動画ファイルのパスを登録
2. 「文字起こし」を実行(39分の動画で約3分)
3. エディタが開いたら:
   - **書き出しタブ**で動画の概要(主題・登場人物・固有名詞)を入力(AI処理の精度が上がる)
   - **レビュータブ**で「指示語を解決」→ 提案を承認/却下(j/k/a/xキーで高速レビュー)
   - **質問タブ**で「固有名詞をスキャン」→ AIからの質問に回答
   - **クリップタブ**で「切り抜き候補を探す」→ 候補を選んでトリム・中抜き→「書き出し」
4. 書き出された動画は動画と同じ場所の `exports/` に保存されます

CLIだけでも使えます:

```bash
uv run python transcribe.py 動画.mov ja          # 文字起こし(.srt/.txt生成)
uv run python resolve_pronouns.py 動画 --form annotate  # 指示語の注釈付け
```

## ライブラリのバージョン制約(重要)

以下の組み合わせは**互換性を実機検証して固定**しています。**個別にアップグレードしないでください**。

| ライブラリ | 制約 | 理由 |
|---|---|---|
| torch / torchaudio | `==2.8.*` (cu128) | pyannote 3.x が torchaudio 2.9+ の削除APIに依存。2.8はBlackwell(sm_120)対応済み |
| pyannote-audio | `>=3.3,<4` | 4.x は規約同意が別途必要な新モデル(community-1)を強制する |
| huggingface-hub | `<1.0` | pyannote 3.x が 1.0 で削除された `use_auth_token` 引数を使う |
| faster-whisper | `>=1.1.0` | torch非依存(CTranslate2)。CUDA 12系で動作 |
| TypeScript | `~5.9` | 6系は openapi-typescript(API型自動生成)と非互換 |
| ffmpeg | 6.x で検証 | select式フィルタに不具合があるため trim+concat 方式を採用済み(対応不要) |

すべての依存は `uv.lock` / `frontend/package-lock.json` でロックされています。
別マシンへは、このフォルダごとコピーして `uv sync && (cd frontend && npm install)` で再現できます。

## 開発

```bash
./dev.sh check    # 全テスト+型チェック+ビルド(backend 407 / frontend 48 / E2E 30)
./dev.sh e2e      # E2Eテスト(FakeLLM+一時DBなのでGPUもLLMも不要)
cd frontend && npm run gen:api   # バックエンドAPIを変えたら型を再生成
```

設計ドキュメント: [DESIGN.md](docs/DESIGN.md)(概要)/ [BACKEND_DESIGN.md](docs/BACKEND_DESIGN.md) /
[FRONTEND_DESIGN.md](docs/FRONTEND_DESIGN.md) / [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)(進捗)。
AIで開発を続ける場合の規約は [CLAUDE.md](CLAUDE.md)。

## 既知の制限(今後の予定)

- 顔検出レイアウトは静的クロップ(クリップ内でカメラが大きく動くと追従しない)。
  検出失敗時はぼかし背景に自動フォールバック
- 複数クリップの一括書き出しUIは未実装
- Windows は未対応
- 話者分離は2人の対談に最適化(3人以上は「話者N」表示)
- ROCm環境ではfaster-whisper(CUDA専用ビルド)が使えないため、
  whisper.cpp(`./dev.sh whispercpp` でビルド。実時間比約11.6倍)か、
  未ビルドなら公式Whisper(約4.4倍)を自動で使う
  (機能は同等。実測値は docs/verify_rocm.md 参照)

## ライセンス

[MIT License](LICENSE)。使用しているモデル・ライブラリには各自のライセンスがあります:

- Whisper / faster-whisper: MIT
- pyannote.audio: MIT(モデル利用にはHuggingFaceでの規約同意が必要)
- Qwen3 (Ollama経由): Apache 2.0
- 文字起こし対象の動画・音声の権利はユーザーに帰属します
