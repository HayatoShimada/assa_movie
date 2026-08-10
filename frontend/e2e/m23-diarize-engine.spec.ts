/** M23: 話者分離のオン・オフが設定タブから保存できる。

エンジンの選択UIは2026-08-10に削除した(実装はONNXの1つだけで、
選べない設定をUIに出していた)。 */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('話者分離を有効にすると話者名まで設定できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  // E2Eサーバーは話者分離を無効で起動するので、まず有効にする
  await page.getByTestId('setting-diarization-enabled').check()
  await page.getByTestId('settings-save').click()

  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values)
    .toMatchObject({ diarization_enabled: true })
})

test('話者分離エンジンの選択UIはもう無い', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  await expect(page.getByTestId('setting-diarization-enabled')).toBeVisible()

  await expect(page.getByTestId('setting-diarization-engine')).toHaveCount(0)
  await expect(page.getByTestId('setting-asr-engine')).toHaveCount(0)
})
