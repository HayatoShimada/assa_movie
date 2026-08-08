/** M26: ライセンスの状態表示と登録(検証はローカルのみ) */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

async function openSettings(page, mediaId: number) {
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  await expect(page.getByTestId('license-panel')).toBeVisible()
}

test('ライセンス: 未登録と表示され、案内が出る', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  await expect(page.getByTestId('license-status')).toHaveText('未登録')
  await expect(page.getByTestId('license-note')).toContainText('登録してください')
})

test('ライセンス: 不正なキーはエラーになり、状態は変わらない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  await page.getByTestId('license-key-input').fill('KS1.でたらめ.きー')
  await page.getByTestId('license-register').click()

  await expect(page.getByTestId('license-error')).toContainText('ライセンスキー')
  await expect(page.getByTestId('license-status')).toHaveText('未登録')
  // 保存されていないこと(APIから見ても未登録)
  expect((await (await request.get(`${API}/api/license`)).json()).status).toBe('missing')
})

test('ライセンス: 正規のキーを登録すると有効になる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  // E2Eサーバーはテスト用の鍵ペアを持っていて、シード用に1本発行できる
  const key = (await (await request.post(`${API}/api/e2e/license-key`)).json()).key
  await openSettings(page, mediaId)

  await page.getByTestId('license-key-input').fill(key)
  await page.getByTestId('license-register').click()

  await expect(page.getByTestId('license-status')).toHaveText('有効')
  await expect(page.getByTestId('license-key-input')).toHaveValue('')
})
