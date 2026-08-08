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

### M24: 名称変更(KirinukiStudio) ✅ 完了

- 表示名(画面のh1・ブラウザタブ・FastAPIのtitle)・README・パッケージ名
  (`kirinuki-studio` / `kirinuki-studio-frontend`)・favicon を差し替えた
- 環境変数の接頭辞を `WL_` → `KS_` に変更。旧接頭辞は pydantic-settings が
  **黙って無視する**ため、設定されていたら起動時に警告する
- `uv init` の残骸だった `src/whisper_local/`(未参照)と Vite テンプレートの
  残骸(react.svg / vite.svg / frontend/README.md)を掃除した

**パスの扱い(既存環境は移さない)**: `backend/core/paths.py` を新設し、
新規インストールでは XDG(`~/.local/share|.cache|.config/kirinuki-studio`)を使う。
ただし既存環境は**そのまま使い続ける**:

| | 既存環境 | 新規インストール |
|---|---|---|
| DB・uploads | リポジトリ直下(`whisper.db`) | `~/.local/share/kirinuki-studio/` |
| モデルキャッシュ | `~/.cache/whisper-local`(3.4GB) | `~/.cache/kirinuki-studio` |

移さない理由は2つ。`media.path` に**絶対パスが入っている**ため uploads(3.9GB)を
移すと既存の動画への参照が全部切れること、モデルキャッシュを見失うと whisper.cpp と
ONNX話者分離が「無い」と判定されて**黙って遅い実装に降格する**こと。
どちらもユーザーには原因が分からない壊れ方をする。

**リポジトリ名とURLは未変更**(参照が切れるため最後に回す)。

### M25: Tauri シェル(Linux) ✅ 完了

`./dev.sh app` でデスクトップアプリとして起動する。実機で確認済み
(ネイティブウィンドウが開き、既存DBのプロジェクト一覧が表示される)。

構成は `frontend/src-tauri/`:

- `src/backend.rs` — Pythonバックエンドの起動・待機・後始末
- `src/lib.rs` — ウィンドウ生成と、確保したポートのwebviewへの注入
- シェルは画面のロジックを一切持たない(画面は今まで通りReact)

**ポートは毎回取り直す。** 固定にすると開発中の `./dev.sh`(8000番)や
他のアプリとぶつかって起動できなくなる。確保したURLは
`window.__KS_API_BASE__` としてwebviewに注入し、
`frontend/src/api/client.ts` の `resolveApiBase()` が読む
(ブラウザ開発時は未定義のままなので、従来通りViteプロキシを使う)。

**CORSが要る。** webviewのページは `tauri://localhost`(Windowsは
`http://tauri.localhost`)で動くので、127.0.0.1のバックエンドを叩くと必ず
クロスオリジンになる。待ち受けはループバックのみなので、この用途の
オリジンだけを許可した(`backend/app.py`)。

**子プロセスの後始末で1つ踏んだ。** Dropはウィンドウを閉じたときには走るが、
SIGTERM・SIGKILL・panicでは走らず、Pythonが残ってポートを掴み続けた。
`prctl(PR_SET_PDEATHSIG)` でカーネルに面倒を見てもらう形に変更。
あわせて、開発時の起動を `uv run` から `.venv/bin/python` の直接実行に変えた
(`uv` を挟むと中間プロセスが1つ増え、親の死がPythonまで伝わらないため)。

**起動中のスプラッシュは未実装。** 現状はバックエンドが応答するまで
ウィンドウを出さない(手元では数秒)。初回のモデル取得を伴う環境での
待ち時間はM28のインストーラ側で扱う。

### M26: ライセンス(Ed25519オフライン検証) ✅ 検証と登録は完了 / 機能制限は未実装

キーの形は `KS1.<ペイロード>.<署名>` の1行。署名対象はペイロードの
base64url文字列そのものにした。JSONを正規化する必要がなくなり、
「送られてきた通りのバイト列」を検証できる。

- `backend/core/license.py` — 検証の純関数(pytest 22件)
- `backend/core/license_key.py` — アプリに埋め込む**公開鍵**(秘匿情報ではない)
- `backend/api/license_api.py` — `GET/POST /api/license`。キー本体は返さない
- `frontend/.../LicensePanel.tsx` — 設定タブの状態表示と登録欄
- `tools/license_tool.py` — 発行側のCLI(keygen / pubkey / issue / check)

**秘密鍵はリポジトリに置かない。** この開発機では `~/.kirinuki-issuer/` に
生成済み(漏れると誰でもキーを発行できる)。

期限切れは即座に締め出さず、30日の猶予期間を設けた(`GRACE_DAYS`)。
更新の行き違いで作業中のユーザーが止まる損失の方が大きいため。
残り14日を切ると画面で知らせる。

**機能制限(未登録なら閲覧のみ)は未実装。** 開発中のこの環境まで止めてしまうため、
どこで線を引くかは配布形態が決まるM28で入れる。現状は状態を出すところまで。

### M27: APIキー設定 + Claudeプロバイダ ✅ 完了(疎通確認ボタンのみ未実装)

- `backend/engines/llm/claude.py` — Anthropic公式SDK経由。構造化出力
  (`output_config.format`)でJSON Schemaをそのまま渡せるので、Ollama・Geminiと
  同じ `complete_json` の形に収まる
- `backend/api/keys_api.py` + `ApiKeysPanel.tsx` — 設定画面からキーを登録・削除

**Claude実装で押さえた点**(`claude-api` スキルより):

- 既定モデルは `claude-opus-5`
- **`max_tokens` は「思考+本文」の合計にかかる。** Claudeは既定で思考するので、
  本文だけを見て詰めると途中で切れる(16000確保)
- **拒否(`stop_reason: "refusal"`)は成功応答で返る。** 本文を読む前に確認しないと
  空配列を正常な結果として扱ってしまう。再試行しても同じなのでその場で伝える
- 構造化出力は全objectに `additionalProperties: false` が要る(`to_strict_schema`)
- チャンクごとに何十回も呼ぶため、effortは既定のhighではなくmedium

**キーの扱い**: この端末の設定ディレクトリに 0600 で置くだけ。画面には
「登録済みかどうか」と末尾4文字しか返さない。環境変数のキーはファイルより優先される
ため、どちらが効いているかを画面に出す(消せるのはファイル側だけ)。

**あわせて直したもの**: 設定APIの `llm_providers[].ready` が、どのクラウド
プロバイダでもGeminiのキーだけを見ていた。プロバイダごとに判定するようにした。

**疎通確認ボタンは未実装。** 実際に課金の発生するリクエストを投げるので、
どのモデル・どの内容で投げるかを決めてから入れる。

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
- M25: ✅ サイドカーの起動・終了・異常終了時の後始末(`cargo test` 9件。親プロセスをkillしてPythonが道連れになることを実機でも確認)
- M26: ✅ 署名検証のテーブル駆動テスト(正規・改竄・期限切れ・別製品のキー。pytest 29件 + E2E 3件)
- M28: クリーンVMでインストールしてOSメニューから起動できること

## 未決事項

- リポジトリ名・配布URL・アイコンのデザイン
- エディション(無料/有料)の線引きと、無料時の機能制限の範囲
- Windows での GPU 既定(CUDA / Vulkan)は M28 の実測で決める
