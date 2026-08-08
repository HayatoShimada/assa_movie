/** M23: 話者分離エンジンの選択(ONNX / pyannote)が設定タブから保存できる */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('話者分離を有効にするとエンジンを選べる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  // E2Eサーバーは話者分離を無効で起動するので、まず有効にする
  const select = page.getByTestId('setting-diarization-engine')
  await expect(select).toBeHidden()
  await page.getByTestId('setting-diarization-enabled').check()
  await expect(select).toBeVisible()

  // 明示的にONNXを選び、保存後にAPIへ反映されること
  await select.selectOption('onnx')
  await page.getByTestId('settings-save').click()
  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values)
    .toMatchObject({ diarization_enabled: true, diarization_engine: 'onnx' })
})
