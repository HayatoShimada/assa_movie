/** M28: セットアップパネル(足りていないモデルの案内と取得) */
import { expect, test } from '@playwright/test'
import { seedTranscribed } from './helpers'

test('セットアップ: 足りないものが案内される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('setup-panel')
  await expect(panel).toBeVisible()

  // 話者分離モデルはその場で取れる
  await expect(page.getByTestId('setup-item-diarization')).toContainText('未取得')
  await expect(page.getByTestId('setup-fetch-diarization')).toBeVisible()

  // 本体が無いwhisper.cppはモデルだけ落としても使えないので取得ボタンを出さない
  await expect(page.getByTestId('setup-item-whispercpp')).toContainText('本体が見つかりません')
  await expect(page.getByTestId('setup-fetch-whispercpp')).toHaveCount(0)
})

test('セットアップ: 3.1GBはGB表記で出す', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  // 「3100MB」では大きさが伝わらない
  await expect(page.getByTestId('setup-item-whispercpp')).toContainText('3.0GB')
})
