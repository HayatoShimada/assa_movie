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

test('セットアップ: 取得すると完了を検知して「準備できています」になる', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  await expect(page.getByTestId('setup-state-diarization')).toContainText('未取得')
  await page.getByTestId('setup-fetch-diarization').click()

  // 完了を待つ状態名がバックエンドとずれていて、取得が終わってもボタンが
  // 「取得中…」のまま固まっていた(v0.9.8まで)。終端の検知そのものを見る
  await expect(page.getByTestId('setup-state-diarization')).toContainText(
    '準備できています',
    { timeout: 20000 },
  )
  await expect(page.getByTestId('setup-fetch-diarization')).toHaveCount(0)
})

test('セットアップ: 3.1GBはGB表記で出す', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  // 「3100MB」では大きさが伝わらない
  await expect(page.getByTestId('setup-item-whispercpp')).toContainText('3.0GB')
})
