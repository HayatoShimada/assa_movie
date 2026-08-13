# macOS での開発・ビルド手順 (MACOS_BUILD.md)

本アプリケーションを macOS (特に Apple Silicon M1/M2/M3 Mac) 上で開発・ビルドするための手順書です。

---

## 1. 前提条件のインストール

macOS でアプリをビルド・起動するためには、以下のツールが必要になります。

### ① Xcode Command Line Tools
Tauri のコンパイルや、C++ のコンパイル環境（Clang）に必要です。ターミナルで以下を実行します。
```bash
xcode-select --install
```

### ② Homebrew
開発ツールをインストールするために使用します（導入済みの場合はスキップしてください）。
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### ③ 必要なパッケージ (FFmpeg, CMake)
動画編集に必要な `ffmpeg` と、`whisper.cpp` のビルドに必要な `cmake` をインストールします。
```bash
brew install ffmpeg cmake
```

### ④ Node.js (v20以上)
フロントエンドの開発環境に必要です。
```bash
brew install node
```

### ⑤ Rust (`rustup`)
Tauri (デスクトップアプリのシェル) のビルドに必須です。
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```
※ インストール完了後、ターミナルを再起動するか `source $HOME/.cargo/env` を実行してパスを通してください。

### ⑥ uv (Python パッケージ管理)
バックエンドの依存関係解決に必要です。
```bash
brew install uv
```

---

## 2. セットアップ手順

プロジェクトディレクトリのルートで、以下の順番にコマンドを実行します。

### ① Python 依存関係の同期
```bash
./dev.sh sync
```
※ `pyproject.toml` は GPU 依存関係（ROCm/CUDA）を含まない設定になっているため、macOS でもそのまま同期が完了します。

### ② フロントエンド依存関係のインストール
```bash
cd frontend
npm install
cd ..
```

### ③ 話者分離モデルの取得
```bash
./dev.sh diarize-models
```

### ④ `whisper.cpp` (Metal) のビルドとモデル取得
Apple Silicon の GPU (Metal) を用いて高速な文字起こしを行うために、`whisper.cpp` をローカルビルドします。
```bash
./dev.sh whispercpp
```
※ 完了すると、`~/.cache/kirinuki-studio/bin/whisper-cli` に Metal をリンクしたバイナリが配置され、モデル (`ggml-large-v3.bin`) がダウンロードされます。

---

## 3. 起動と開発

### 開発用サーバーの同時起動 (Web / バックエンド)
```bash
./dev.sh
```
ブラウザで <http://localhost:5173> を開くことで開発・動作確認が可能です。

### デスクトップアプリ (Tauri) として起動
```bash
./dev.sh app
```
※ Xcode コマンドラインツールを通じて、ローカルの Mac アプリケーションウィンドウが立ち上がります。

---

## 4. パッケージングと配布ビルド (.dmg)

macOS 向けのスタンドアロンアプリ (`.app` および `.dmg` インストーラ) をパッケージングします。

```bash
./dev.sh package
```

ビルドが成功すると、以下のパスに `.dmg` ファイルが生成されます。
`frontend/src-tauri/target/release/bundle/dmg/KirinukiStudio_*.dmg`

> [!NOTE]
> **コード署名（Code Signing）について**
> ローカルで開発者証明書（Apple Developer Program）を設定していない場合、Ad-hoc 署名（無署名）でビルドされます。
> 署名なしの DMG から他の Mac にインストールしたアプリを起動する際、「開発元が未確認のため開けません」という警告が出る場合があります。その場合は、Mac の `システム設定` -> `プライバシーとセキュリティ` から `このまま開く` を選択して許可してください。
