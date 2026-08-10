/** M16: 設定タブの実行環境パネル(確定プロファイルの表示・再検出・おすすめ適用) */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('実行環境パネル: 確定した構成が表示される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('environment-panel')
  await expect(panel).toBeVisible()
  // OS×GPUのプロファイルと、そこから決まる文字起こしの構成を1行ずつ出す
  await expect(page.getByTestId('env-profile')).toContainText(/Linux|Windows|macOS/)
  await expect(page.getByTestId('env-resolved')).toContainText(/whisper\.cpp|faster-whisper/)
  await expect(page.getByTestId('env-recommendation')).toContainText(/large-v3/)
  await expect(panel).toContainText('動画エンコード')
  await expect(panel).toContainText('Ollama')
})

test('実行環境パネル: 再検出してもプロファイルが表示され続ける', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  await expect(page.getByTestId('env-profile')).toBeVisible()

  await page.getByTestId('env-redetect').click()

  await expect(page.getByTestId('env-profile')).toContainText(/Linux|Windows|macOS/)
  await expect
    .poll(async () => (await (await request.get(`${API}/api/environment`)).json()).profile.os)
    .toBeTruthy()
})

test('実行環境パネル: おすすめ設定を適用してもエンジンは書き込まれない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const rec = (await (await request.get(`${API}/api/environment`)).json()).recommendations
  await page.getByTestId('env-apply-recommendation').click()

  // モデルは推奨どおりに保存する。エンジンは実行環境の対応表が決めるので
  // 設定には現れない(v0.9.5でここに具体名を書き、同梱物が増えても
  // 追従せずGPUがあっても遅いエンジンが使われ続けた)
  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values)
    .toMatchObject({ asr_model: rec.asr_model })
  const values = (await (await request.get(`${API}/api/settings`)).json()).values
  expect(values).not.toHaveProperty('asr_engine')
})
