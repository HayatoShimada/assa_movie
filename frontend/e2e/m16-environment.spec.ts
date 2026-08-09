/** M16: 設定タブの環境パネル(スキャン結果表示・VRAM割当・おすすめ適用) */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('環境パネル: スキャン結果とおすすめが表示される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('environment-panel')
  await expect(panel).toBeVisible()
  // GPU情報は子プロセスで調べるため初回は数秒かかる
  // おすすめ行にはASRモデルが必ず入る(GPU有無に依らず)
  await expect(page.getByTestId('env-recommendation')).toContainText(/large-v3/, {
    timeout: 30000,
  })
  await expect(panel).toContainText('GPU')
  await expect(panel).toContainText('動画エンコード')
  await expect(panel).toContainText('Ollama')
})

test('環境パネル: おすすめ設定を適用してもエンジンは自動選択のまま', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const rec = (await (await request.get(`${API}/api/environment`)).json()).recommendations
  await page.getByTestId('env-apply-recommendation').click()

  // モデルは推奨どおりに保存するが、エンジンは具体名で固定しない。
  // 固定すると同梱物が増えて推奨が変わっても追従せず、GPUがあっても
  // 遅いエンジンが使われ続ける(v0.9.5〜v0.9.8で実際にそうなっていた)
  await expect
    .poll(async () => {
      const values = (await (await request.get(`${API}/api/settings`)).json()).values
      return { model: values.asr_model, engine: values.asr_engine }
    })
    .toEqual({ model: rec.asr_model, engine: 'auto' })
})
