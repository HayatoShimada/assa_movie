import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // 画面に組み込んだJSの依存(React・BudouXなど)のライセンス表記を出力する。
    // 圧縮で @license コメントは消えるので、ここで集めて配布物に同梱する
    license: { fileName: 'licenses/javascript-THIRD-PARTY-NOTICES.md' },
  },
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    port: 5173,
    // バックエンドAPIへプロキシ。フロントは常に同一オリジンで /api を叩く(CORS不要)。
    // E2EはVITE_API_PORT=8001でFakeLLMバックエンドに向ける。
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.VITE_API_PORT ?? 8000}`,
        changeOrigin: true,
      },
    },
  },
})
