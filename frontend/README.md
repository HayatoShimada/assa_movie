# KirinukiStudio フロントエンド

React 19 + Vite + TypeScript + Tailwind v4。バックエンド(FastAPI)は `../backend`。

起動やテストはリポジトリ直下の `./dev.sh` から行うのが基本です。
設計は [../docs/FRONTEND_DESIGN.md](../docs/FRONTEND_DESIGN.md)、規約は
[../CLAUDE.md](../CLAUDE.md) を参照してください。

## コマンド

```bash
npm run dev       # 開発サーバー(5173)。バックエンドは別途 ./dev.sh api
npm run check     # 型・lint・ユニットテスト・ビルドを通す
npm run e2e       # Playwright(FakeLLM・一時DBなのでGPUもOllamaも不要)
npm run gen:api   # バックエンドのAPIから型を再生成(API変更時は必須)
```

## 構成

| ディレクトリ | 中身 |
|---|---|
| `src/api/` | 型付きクライアント。`schema.d.ts` は自動生成物なので手で編集しない |
| `src/components/` | 画面の部品(タブごとにディレクトリを分ける) |
| `src/pages/` | ルーティングの単位(`Home` / `Editor`) |
| `src/lib/` | 純関数(字幕レイアウト計算など)。テストしやすい形に寄せる |
| `e2e/` | Playwright。UIを変えたらここにも追加する |
