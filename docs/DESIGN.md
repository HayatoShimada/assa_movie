# KirinukiStudio

UIで実行・操作できる、自動切り抜き動画作成アプリ。

## コンセプト

長尺の対談・イベント動画から、文字起こし→話者分離→字幕→切り抜き候補の提案までを
ローカルで一気通貫処理し、プレビューを見ながら短尺動画を量産できるツール。
音声も動画も外に出さない(LLMだけは利用者の選択でクラウドにできる)。

## 機能

### 文字起こし・字幕
- 字幕生成: 表示位置をUIで制御。フォント・色・背景・話者ごとの色分けを設定可能。
  px値は1920×1080基準で保存し、出力解像度へ比率換算する
- 折返し・禁則: 日本語の行頭・行末禁則に対応。判定はPythonとTypeScriptの両方にあり、
  ケース表(`tests/fixtures/subtitle_wrap_cases.json`)を共有して見た目を揃える
- 指示語置換: 指示語(これ・それ・あれ)を指す内容で補足。
  積極性3段階(強/中/弱)× 表現形式(カッコ注釈/置換/補完)。
  **LLMは提案するだけで、適用は機械ガードを通ったものだけ**(`pipeline/pronoun.py`)
- フィラー排除: 「なんか」「まあ」「その」等の言い淀みを字幕から除去。
  無効/弱(安全な間投詞のみ)/強(単語確率とポーズも見る)
- 固有名詞の対話的修正: 表記が確定できない固有名詞(例: 半導体/反動体)をLLMが質問し、
  回答で全出現箇所を一括修正+用語集登録(以後の文字起こしのpromptにも反映)
- 字幕採用ジャッジ: 「聞き取りにくい箇所・固有名詞・理解に必要な文脈」を自動で選び、
  1件ずつ手動で切替できる。採用率は設定で調整する
- 話者分離: 話者数・表示名をUIで設定可能。相槌は字幕から常に除外する

### 切り抜き
- アテンション機能: 切り抜きできそうな位置をスコアの根拠付きで提案し、プレビューを見ながら選択・作成
- クリップ単位の再調整: 前後トリム(自然な切れ目にスナップ)・中抜き(ジェットカット)・
  クリップ内指示語の自己完結化・フックテキスト編集
- 向き変換(横→縦 等): 中央クロップ / ぼかし余白 / 顔検出の3方式。クリップ単位で上書きできる
- タイトル・概要欄・ハッシュタグの自動生成
- 高速書き出し: 一つの動画から複数の切り抜きを一括生成

### 実行環境
- **ローカル動作が既定。** LLMだけクラウドAPI(Gemini / Claude)に切替できる
- GPUはCUDA・ROCm・Vulkan・Metalに対応(下の「ASRエンジンの選択」を参照)

## アーキテクチャ

詳細設計: [BACKEND_DESIGN.md](BACKEND_DESIGN.md) / [FRONTEND_DESIGN.md](FRONTEND_DESIGN.md)
実装の記録: [V1_PLAN.md](V1_PLAN.md)(マイルストーン別・受け入れ基準付き)

```
┌─ デスクトップシェル: Tauri v2(Rust)
│   ・画面は持たない。Pythonを空きポートで子プロセス起動し、webviewにURLを渡すだけ
│   ・終了時に子プロセスを確実に殺す(WindowsはJob Object、UNIXはプロセスグループ)
├─ フロントエンド: React + TypeScript(webview内)
│   ・動画プレビュー: HTML5 <video> + CSSオーバーレイ字幕
│   ・進捗表示: SSEでバックエンドから受信
├─ バックエンド: Python + FastAPI(配布時はPyInstallerで1ファイル)
│   ・文字起こし: whisper.cpp / faster-whisper(GPUで自動選択)
│   ・話者分離: sherpa-onnx(ONNX。torch不要・トークン不要)
│   ・指示語置換: ローカルLLM(Ollama)/ クラウドAPIを切替可能
│   ・書き出し: ffmpeg(Windowsは同梱、他OSはシステムのもの)
└─ 配布: .exe(NSIS) / .deb / .AppImage / .dmg
```

## 決定の記録

過去に選んだ理由が残っていると、同じ検討を繰り返さずに済む。日付は決めた日。

### 2026-08-07 Tauriで包む(ブラウザで開く形をやめた)

当初は「`uv run` で起動 → ブラウザで localhost を開く」形だった。
インストールして使う人はターミナルを開かないので、実行ファイル1つで完結させる。
Tauriを選んだのはElectronよりバイナリが小さく、Rust側で子プロセスの後始末を
確実に書けるため。**シェルは画面を持たない**設計にして、UIはすべてWeb側に置いた。

MVPをGradioで先行実装する案もあったが、結局Reactに作り直すことになるので採らなかった。

### 2026-08-07 ASRエンジンをGPUで自動選択する

faster-whisper(CTranslate2)はCUDA専用ビルドなので、AMD環境では初期化に失敗する。
かといってエンジンを利用者に選ばせると、選択を誤ったまま「遅い」「動かない」になる。
`asr_engine=auto` で環境から決める:

| 環境 | 選ぶもの | 理由 |
|---|---|---|
| CUDA | faster-whisper (float16) | CUDA版CTranslate2が最速 |
| ROCm | whisper.cpp | CTranslate2が使えない |
| GPUあり・CUDA/ROCmでない | whisper.cpp (Vulkan) | AMDのWindows機が該当。実測でCPUの11倍 |
| GPUなし | faster-whisper (int8) | CPUでint8は安全(int8クラッシュはBlackwell GPU限定) |

モデルは large-v3 が既定(精度優先・単語タイムスタンプ必須)。

### 2026-08-08 話者分離をpyannoteからONNXへ

| エンジン | 実時間比 | 依存 | HFトークン |
|---|---|---|---|
| sherpa-onnx | 10.7倍 | 76MBのONNX | 不要 |
| pyannote | 2.8倍 | torch 14GB | 必要 |

話者割り当ての一致率94.8%で、速く・軽く・トークンも要らない。
モデル76MBは配布物に同梱できる大きさなので、入れた直後から話者分離が使える。

### 2026-08-08 配布物にtorchを入れない

torchだけで11.5GB、入れなければ644MB。`[project.dependencies]` はtorch非依存の
ものだけにし、torch系は開発専用のグループに置く。GPU検出もtorchではなく
`rocm-smi`/`nvidia-smi`/レジストリから読む(torchに聞くと5秒、CLIなら120ms)。

**2026-08-09に、torchを使う2エンジン(transformers版Whisper / pyannote)を削除した。**
配布版では一度も動かず「選べるのに選ぶと落ちる」選択肢になっていたため。

### 2026-08-09 ffmpegはWindowsだけ同梱する

一般に配布されているビルドは110MB・GPL(libx264入り)。使う機能だけに絞って
自前でビルドし、35MB・LGPL v2.1にした。LinuxとmacOSはOSのパッケージで入るので同梱しない
(AppImageだけは依存を宣言できないため、書き出し時に導入手順を案内する)。

## 制約・技術メモ

- **Blackwell世代GPUではint8がクラッシュする**ため compute_type は float16 固定
- **whisper.cppは `--output-json-full` で呼ぶ(`-ml` を付けない)。**
  `-ml` を付けると句読点が落ちる(実測)。セグメント分割は自前で行う
- **Windowsのロケール依存エンコーディングで5回踏んでいる。**
  出力は `force_utf8_stdio()`、入力は `SUBPROCESS_TEXT`、
  ファイルは `encoding="utf-8"` を必ず明示する(テストで見張っている)
- 依存バージョンは固定(torch 2.8 / TypeScript 5.9)。上げない

## 対応環境

Windows / Ubuntu / macOS (Apple Silicon)。
