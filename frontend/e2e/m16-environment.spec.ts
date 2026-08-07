/** M16: 設定タブの環境パネル(スキャン結果表示・VRAM割当・おすすめ適用) */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('環境パネル: スキャン結果とおすすめが表示される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('environment-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('GPU')
  await expect(panel).toContainText('動画エンコード')
  await expect(panel).toContainText('Ollama')
  // おすすめ行にはASRモデルが必ず入る(GPU有無に依らず)
  await expect(page.getByTestId('env-recommendation')).toContainText(/large-v3/)
})

test('環境パネル: おすすめ設定を適用するとASR設定が変わる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const rec = (await (await request.get(`${API}/api/environment`)).json()).recommendations
  await page.getByTestId('env-apply-recommendation').click()

  await expect
    .poll(async () => {
      const values = (await (await request.get(`${API}/api/settings`)).json()).values
      return { model: values.asr_model, engine: values.asr_engine }
    })
    .toEqual({ model: rec.asr_model, engine: rec.asr_engine })
})
