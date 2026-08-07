import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
