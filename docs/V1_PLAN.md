# KirinukiStudio v1.0.0 実装計画

## Context

v0.4.0 まではローカル開発用のWebアプリ(FastAPI + React をブラウザで開く)だった。
v1.0.0 では**配布可能なデスクトップアプリ**にする。ユーザーの要件は次の7点。

1. 名称変更(→ **KirinukiStudio**)
2. Ubuntu / Linux インストーラー
3. Windows 対応
4. GUI 動作(ブラウザを開かない)
5. OS のアプリとして登録(メニュー・アイコン・関連付け)
6. インストール時にライセンスキー登録
7. Gemini と Claude の API キーを設定画面で登録

GUI は **Tauri v2**(ユーザー選択)。ライセンス方式は下記の通り**オフライン署名検証**を採用する。

## 最大の制約: 配布サイズ(実測)

| 対象 | サイズ |
|---|---|
| `.venv`(ROCm版torch含む) | **14GB** |
| whisper.cpp + ggmlモデル | 3.4GB |
| HuggingFaceキャッシュ | 2.9GB |

**全部入りインストーラーは成立しない。** そして 14GB の大半は torch で、
ASR を whisper.cpp に移した今、**torch が要るのは話者分離(pyannote)だけ**。

→ 方針: **torch を外せるか検証する**(M23)。外せれば配布物は数百MBに収まり、
初回起動時の巨大ダウンロードも不要になる。外せない場合は初回起動時に
GPUに応じて導入する方式にフォールバックする。

## ライセンス方式の決定(オフライン署名検証)

**Ed25519 署名付きライセンスキーを、アプリ内蔵の公開鍵でオフライン検証する。**

- キーの中身: `{製品, エディション, 発行日, 有効期限?, ライセンシー, 台数ヒント}` + 署名
- アプリは**公開鍵のみ**を持つ。秘密鍵は発行側だけが持つ
- 検証は完全にローカル。ネットワーク接続を一切必要としない

**この方式を選ぶ理由:**
- このアプリの価値は「データを外に出さないこと」。認証のためだけにサーバー通信を
  発生させるのは製品思想と矛盾する
- サーバーの運用コスト・障害時にアプリが起動しないリスクを負わない
- オフライン利用(撮影現場・機内など)を阻害しない

**トレードオフ(承知の上):**
- 失効(revoke)ができない。→ 有効期限付きキーで実質的に対応する
- キーの共有を技術的に防げない。→ マシンIDのハッシュを**警告表示のみ**に使い、
  ハード制限はしない(正規ユーザーがマシン更新時に締め出される損失の方が大きい)
- 将来オンライン認証が必要になったら、この方式の上に足せる(逆は難しい)

**保存場所**: OSの資格情報ストア(Tauri の keyring プラグイン)。
平文の設定ファイルには置かない。APIキーも同じ場所に置く。

## アーキテクチャ(Tauri + サイドカー)

```
┌─ Tauri (Rust, ~15MB) ──────────────────────────┐
│  WebView: ビルド済みReact(現行をそのまま流用)   │
│  ・ライセンス検証(Ed25519)                     │
│  ・資格情報ストア(APIキー・ライセンス)          │
│  ・サイドカーの起動/停止・ヘルスチェック          │
└───────────────┬────────────────────────────────┘
                │ localhost HTTP(現行APIのまま)
┌───────────────▼────────────────────────────────┐
│ サイドカー: FastAPI(PyInstallerで単一実行体)   │
│  + whisper.cpp バイナリ                         │
│  + ffmpeg                                       │
└─────────────────────────────────────────────────┘
```

現行の React / FastAPI のコードは**ほぼそのまま使える**のが利点。
ブラウザ版も維持できる(開発時は `./dev.sh` のまま)。

## マイルストーン

### M23: torch 依存の切り離し(話者分離) ✅ 完了

**結果: sherpa-onnx が全項目で pyannote 以上だったので既定を切り替えた。**

2026-08-08 実測(300秒の対談音声 / Ryzen 16スレッド + RX 7900 XTX):

| | sherpa-onnx | pyannote |
|---|---|---|
| 速度 | **実時間比 10.7倍**(CPUのみ) | 2.8倍(GPU) |
| モデルサイズ | **76MB** | torch 14GB が前提 |
| HFトークン | **不要** | 必要(利用規約への同意も) |
| 話者割り当ての一致率 | 94.8%(基準= pyannote) | ― |

実装:
- `backend/engines/diarize/onnx.py` — sherpa-onnx エンジン
- `backend/engines/diarize/registry.py` — `diarization_engine`(auto|onnx|pyannote)。
  auto はモデルがあれば onnx、無ければ HFトークン次第で pyannote、どちらも無ければ
  話者分離なしで文字起こしを続行する
- `backend/engines/diarize/labels.py` — 話者名の割り当てをエンジンから分離
- `backend/pipeline/pitch.py` — `torchaudio.detect_pitch_frequency` を YIN(numpy)に置換。
  これが話者分離まわりで最後に残っていた torch 依存だった
- `./dev.sh diarize-models` でモデル取得(76MB)

**torch がまだ要る場所**: ASR。ROCm では whisper.cpp(外部ビルド・torch不要)が
最速なので、ASR も whisper.cpp を既定にできれば torch は完全に optional にできる。
CUDA機は faster-whisper(torch不要・CTranslate2)なので、こちらも外せる。
→ 残りは M28 の配布構成で詰める。

### M24: 名称変更(KirinukiStudio)

- 表示名・ウィンドウタイトル・README・パッケージ名・アイコン
- リポジトリ名とURLは最後(参照が切れるため)
- DB・設定ファイルのパスも `kirinuki-studio` に統一(移行コードを入れる)

### M25: Tauri シェル(Linux)

- `sudo apt install libwebkit2gtk-4.1-dev build-essential curl file libssl-dev libayatana-appindicator3-dev librsvg2-dev` と Rust ツールチェーン(未導入)
- `src-tauri/` を追加。WebView は `frontend/dist` を読む
- サイドカー起動: 空きポートを選び、起動を待ち、終了時に確実に落とす
- 起動中のスプラッシュ(初回はモデル取得があるため進捗を出す)

### M26: ライセンス(上記方式)

- `backend/core/license.py`: 署名検証の純関数(テーブル駆動テスト)
- 発行用CLI(社内用): 秘密鍵でキーを発行する
- 初回起動時にキー入力画面。未登録なら機能制限(閲覧のみ)
- 有効期限切れの猶予期間と、期限が近いときの通知

### M27: APIキー設定(Gemini / Claude)

- 設定画面から入力し、資格情報ストアに保存(現行の `gemini_api_key.txt` は移行して廃止)
- **Claude(Anthropic)をLLMプロバイダとして追加**。既存の `PROVIDERS` に足す
  (`backend/engines/llm/registry.py`。実装前に `claude-api` スキルを読むこと)
- キーの疎通確認ボタン(1回だけ最小のリクエストを投げて成否を出す)

### M28: インストーラーとOS登録

- Linux: `.deb` と AppImage(Tauri が生成)。`.desktop` とアイコンで
  アプリメニューに登録。`ffmpeg` は依存として宣言
- Windows: MSI/NSIS。**ROCm は Windows で使えない**ため、
  NVIDIA(CUDA)/ CPU / whisper.cpp の Vulkan バックエンドから自動選択する
  (要検証: Vulkan版whisper.cppの速度)
- 初回起動時のモデル取得(whisper.cpp の ggml、話者分離モデル)に進捗UIを付ける

### M29: 通し検証とリリース

- クリーンな環境(コンテナ/VM)でインストール → ライセンス登録 → 文字起こし →
  書き出し まで通す
- Windows は実機かVMで同様に確認
- `./dev.sh check` と E2E が引き続き通ること

## 検証

- M23: 実データで pyannote と ONNX の話者割り当てを比較(セグメント単位の一致率)
- M25: サイドカーの起動・終了・異常終了時の後始末をE2Eで確認
- M26: 署名検証のテーブル駆動テスト(正規・改竄・期限切れ・別製品のキー)
- M28: クリーンVMでインストールしてOSメニューから起動できること

## 未決事項

- リポジトリ名・配布URL・アイコンのデザイン
- エディション(無料/有料)の線引きと、無料時の機能制限の範囲
- Windows での GPU 既定(CUDA / Vulkan)は M28 の実測で決める
