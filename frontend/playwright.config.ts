import { defineConfig, devices } from '@playwright/test'

/**
 * E2Eテスト設定。
 *
 * バックエンドは e2e 用の一時DBで起動し、本番のwhisper.dbを汚さない。
 * LLMはFakeを使うため、Ollama/Geminiが無くてもE2Eは通る。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // 単一バックエンドを共有するので直列実行
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
      // E2E用バックエンド(FakeLLM・一時DB)
      command: 'uv run python -m backend.e2e_server',
      cwd: '..',
      port: 8001,
      reuseExistingServer: !process.env.CI,
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
