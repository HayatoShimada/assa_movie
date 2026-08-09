import { defineConfig, devices } from '@playwright/test'

/**
 * E2Eテスト設定。
 *
 * バックエンドは e2e 用の一時DBで起動し、本番のwhisper.dbを汚さない。
 * LLMはFakeを使うため、Ollama/Geminiが無くてもE2Eは通る。
 */
export default defineConfig({
  testDir: './e2e',
  // 全テストが単一バックエンド(共有DB)を使うため、ファイル間も含め完全直列にする。
  // workers: 1 が無いとファイル単位で並列になり、resetが互いのデータを消して壊れる
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://localhost:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'ja-JP',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // E2E用バックエンド(FakeLLM・一時DB)。
      // 起動方法を差し替えられるようにしておく(venvを自分で用意した場合など)
      // 例: KS_E2E_BACKEND=".venv/Scripts/python.exe -m backend.e2e_server"
      command: process.env.KS_E2E_BACKEND ?? 'uv run python -m backend.e2e_server',
      cwd: '..',
      port: 8001,
      // 既に8001に居るサーバを使い回さない。**古いコードのサーバに対して
      // テストが通ってしまう**ため(バックエンドを直したのに全部緑になり、
      // 落として起動し直したら起動すらしなかった)。使用中ならエラーで止める
      reuseExistingServer: false,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'npm run dev -- --port 5174 --strictPort',
      port: 5174,
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_PORT: '8001' },
    },
  ],
})
