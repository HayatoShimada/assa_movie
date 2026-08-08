/** M28: セットアップパネル(足りていないモデルの案内と取得) */
import { expect, test } from '@playwright/test'
import { seedTranscribed } from './helpers'

test('セットアップ: 足りないものが案内され、取得できないものにはボタンが出ない', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('setup-panel')
  await expect(panel).toBeVisible()

  // whisper.cppはビルドが要るのでアプリからは入れられない。案内だけ出す
  await expect(page.getByTestId('setup-item-whispercpp')).toContainText('./dev.sh whispercpp')
  await expect(page.getByTestId('setup-fetch-whispercpp')).toHaveCount(0)
})
