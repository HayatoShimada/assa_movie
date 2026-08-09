/**
 * M32: オープンソースソフトウェアの表記。
 *
 * FFmpegはLGPLなので、同梱していること・ライセンス・ソースの入手先が
 * 利用者から見える必要がある。画面から消えていないことを見張る。
 */
import { expect, test } from '@playwright/test'
import { seedTranscribed } from './helpers'

test('設定タブに同梱物のライセンス表記が出る', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('oss-panel')
  await expect(panel).toBeVisible()

  // FFmpegはLGPL。ライセンス名とソースの入手先が揃っていること
  const ffmpeg = page.getByTestId('oss-ffmpeg')
  await expect(ffmpeg).toContainText('FFmpeg')
  await expect(ffmpeg).toContainText('LGPL v2.1')
  await expect(ffmpeg).toContainText('ffmpeg.org')

  await expect(page.getByTestId('oss-whisper.cpp')).toContainText('MIT')
  // 全文の在り処も伝える(同梱しているので配布物の中にある)
  await expect(panel).toContainText('licenses/')
})

test('同梱しているものが漏れなく挙がっている', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const panel = page.getByTestId('oss-panel')
  // 話者分離モデルとPython依存が一覧から抜けていた。
  // 実際には全OSに同梱していて、Apache-2.0は本文の同梱も条件になっている
  await expect(panel).toContainText('Apache-2.0')
  await expect(panel).toContainText('3D-Speaker')
  await expect(panel).toContainText('CNRS')
  await expect(panel).toContainText('Pythonの依存パッケージ')

  // whisper.cppは3OSすべてに同梱している(「Linux版・macOS版」は古い記述だった)
  await expect(page.getByTestId('oss-whisper.cpp')).toContainText('全OSに同梱')

  await expect(panel.locator('li')).toHaveCount(5)
})
