/**
 * M41: 書き出しとクリップ画面の分かりやすさ(v2.0 初心者向け)。
 *
 * - 書き出し後に保存先・ファイル名・「フォルダを開く」「再生」が出る
 * - 動画の概要は最初に開く文字起こしタブにある
 * - 書き出しタブの秒指定は「詳細」に畳まれている
 * - プレビューの字幕が再生操作と重ならない
 * - クリップの範囲バーが動画の長さを超えない・入力欄にラベルがある
 *
 * E2Eの書き出しは疑似処理(ffmpegを使わない)。保存先とファイル名は本物と
 * 同じ関数で決まる。「フォルダを開く」は開発機のファイラーを起動せず記録だけする。
 */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('クリップの書き出し後に保存先とファイル名が出て、フォルダを開ける', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  const clip = await (
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 8, title: '書き出すクリップ' },
    })
  ).json()

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('書き出すクリップ').click()
  await page.getByTestId('clip-export').click()

  const result = page.getByTestId('clip-export-result')
  await expect(result).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('clip-export-result-name')).toHaveText(
    `sample_0s-8s_clip${clip.id}.mp4`,
  )
  // 保存先はフルパス(元動画の隣の exports/)
  await expect(page.getByTestId('clip-export-result-folder')).toHaveText(/[\\/]exports$/)

  await page.getByTestId('clip-export-result-reveal').click()
  await expect
    .poll(async () => (await (await request.get(`${API}/api/e2e/revealed`)).json()).length)
    .toBe(1)
  const [revealed] = await (await request.get(`${API}/api/e2e/revealed`)).json()
  expect(revealed).toMatch(new RegExp(`sample_0s-8s_clip${clip.id}\\.mp4$`))

  // 再生は画面内で(書き出した動画そのものを読む)
  await page.getByTestId('clip-export-result-play').click()
  await expect(page.getByTestId('clip-export-result-video')).toHaveAttribute(
    'src',
    /\/api\/jobs\/\d+\/output$/,
  )
})

test('動画の概要は文字起こしタブの先頭にあり、未入力なら目立たせる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)

  // 最初に開くタブの先頭に1行の帯で出る。未入力なら「未入力」と精度の案内
  const toggle = page.getByTestId('brief-toggle')
  await expect(toggle).toContainText('未入力')
  await expect(toggle).toContainText('AIの精度が上がります')
  await toggle.click()
  await page.getByTestId('brief-theme').fill('古着屋とAIの対談')
  await page.getByTestId('brief-people').click() // blurで保存
  await expect
    .poll(async () => (await (await request.get(`${API}/api/media/${mediaId}/brief`)).json()).theme)
    .toBe('古着屋とAIの対談')

  // 入力済みなら主題が帯に出る
  await page.reload()
  await expect(toggle).toContainText('古着屋とAIの対談')
  await expect(toggle).not.toContainText('未入力')
  await expect(page.getByTestId('brief-theme')).toHaveCount(0)

  // 書き出しタブにはもう無い
  await page.getByTestId('tab-export').click()
  await expect(page.getByTestId('brief-panel')).toHaveCount(0)
})

test('書き出しタブはクリップタブへ案内し、秒指定の書き出しは詳細に畳む', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-export').click()

  await expect(page.getByTestId('export-guide')).toContainText('クリップタブ')
  await expect(page.getByTestId('export-start')).toBeHidden()
  await page.getByText('詳細: 開始秒と終了秒を指定して書き出す').click()
  await expect(page.getByTestId('export-start')).toBeVisible()

  await page.getByTestId('export-end').fill('5')
  await page.getByTestId('export-run').click()
  await expect(page.getByTestId('export-result-name')).toHaveText('sample_0s-5s.mp4', {
    timeout: 15000,
  })

  await page.getByTestId('export-go-clips').click()
  await expect(page.getByTestId('tab-clips')).toHaveAttribute('aria-current', 'page')
})

test('プレビューの字幕は再生操作と重ならない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)

  const frame = (await page.getByTestId('player-frame').boundingBox())!
  const controls = (await page.getByTestId('player-controls').boundingBox())!
  const overlay = page.getByTestId('subtitle-overlay')
  await expect(overlay).toBeVisible()
  const sub = (await overlay.boundingBox())!

  // 再生操作は映像の枠の外(下)にあり、字幕は枠の中に収まる
  expect(controls.y).toBeGreaterThanOrEqual(frame.y + frame.height - 1)
  expect(sub.y + sub.height).toBeLessThanOrEqual(frame.y + frame.height + 1)
  await expect(page.getByTestId('player-play')).toHaveAttribute('aria-label', '再生')
})

test('クリップの範囲バーは動画の終わりを超えず、タイトルとフックにラベルがある', async ({
  page,
  request,
}) => {
  // シードの動画は120秒(2:00)
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/media/${mediaId}/clips`, {
    data: { start: 100, end: 118, title: '終盤のクリップ' },
  })
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('終盤のクリップ').click()

  const labels = page.getByTestId('clip-timeline').locator('xpath=..').locator('span')
  await expect(labels.last()).toHaveText('2:00') // 余白を付けても動画の長さで止まる

  await expect(page.getByLabel(/^タイトル/)).toHaveValue('終盤のクリップ')
  await page.getByLabel(/^フック/).fill('最後に明かされる答え')
  await page.getByLabel(/^タイトル/).click() // blurで保存
  await expect
    .poll(async () => {
      const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
      return clips[0].hook_text
    })
    .toBe('最後に明かされる答え')
})
