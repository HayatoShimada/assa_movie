/**
 * M42: プレビューの字幕を、書き出しと同じ libass で描いた画像にする(issue #4)。
 *
 * 以前はCSSで字幕を描いていた。同じ「48px」でも、書き出し(ASSのFontsize=行の高さ)は
 * 1文字約33px、プレビュー(CSSのfont-size=文字の大きさ)は48pxの太字で、
 * 約1.45倍大きく見えていた。表示時間・フィラー除去・字幕位置の既定も別々だった。
 *
 * いまは画面側で見た目を計算しない。バックエンドが書き出しと同じ材料で作る
 * 時刻表のとおりに、libassで描いた透過画像を枠いっぱいに重ねる。
 * (E2Eの画像は透明な1枚に差し替え。描いた中身が書き出しと同じ画素になることは
 * tests/pipeline/test_subtitle_preview.py が確かめる)
 */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('字幕はCSSの文字ではなく、枠いっぱいに重ねた画像で出る', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  const preview = await (await request.get(`${API}/api/media/${mediaId}/subtitle-preview`)).json()
  await page.goto(`/#/media/${mediaId}`)

  const overlay = page.getByTestId('subtitle-overlay')
  await expect(overlay).toBeVisible()
  expect(await overlay.evaluate((el) => el.tagName)).toBe('IMG')
  await expect(overlay).toHaveAttribute('data-key', preview.events[0].key)
  // 読み上げ・画像が出ないとき用に、折り返し済みの文を代替文字として持つ
  await expect(overlay).toHaveAttribute('alt', preview.events[0].text)
  await expect(overlay).toHaveAttribute(
    'src',
    new RegExp(`/api/media/${mediaId}/subtitle-preview/${preview.events[0].key}\\.png`),
  )

  // 枠は書き出される動画と同じ縦横比で、画像はその枠とぴったり重なる
  const frame = (await page.getByTestId('player-frame').boundingBox())!
  const box = (await overlay.boundingBox())!
  expect(frame.width / frame.height).toBeCloseTo(preview.width / preview.height, 2)
  for (const key of ['x', 'y', 'width', 'height'] as const) {
    expect(Math.abs(box[key] - frame[key])).toBeLessThanOrEqual(1)
  }
})

test('縦向きのプロジェクトは枠も画像も縦(1080×1920)', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request, 'portrait')
  const preview = await (await request.get(`${API}/api/media/${mediaId}/subtitle-preview`)).json()
  expect([preview.width, preview.height]).toEqual([1080, 1920])

  await page.goto(`/#/media/${mediaId}`)
  await expect(page.getByTestId('subtitle-overlay')).toBeVisible()
  const frame = (await page.getByTestId('player-frame').boundingBox())!
  expect(frame.width / frame.height).toBeCloseTo(1080 / 1920, 2)
})

test('字幕の設定を変えると、プレビューの画像も描き直される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  const overlay = page.getByTestId('subtitle-overlay')
  await expect(overlay).toBeVisible()
  const before = (await overlay.getAttribute('data-key'))!

  await page.getByTestId('tab-settings').click()
  const slider = page.getByTestId('setting-subtitle-font-size')
  await slider.fill('62')
  await slider.dispatchEvent('mouseup')
  await page.getByTestId('settings-save').click()

  await expect(overlay).not.toHaveAttribute('data-key', before)
  const preview = await (await request.get(`${API}/api/media/${mediaId}/subtitle-preview`)).json()
  await expect(overlay).toHaveAttribute('data-key', preview.events[0].key)
})

test('文字起こしを手で直すと、プレビューの字幕も変わる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  const segments = await (await request.get(`${API}/api/media/${mediaId}/segments`)).json()
  await page.goto(`/#/media/${mediaId}`)
  const overlay = page.getByTestId('subtitle-overlay')
  await expect(overlay).toBeVisible()
  const before = (await overlay.getAttribute('alt'))!

  // 画面からの手直しと同じAPI。画面は文字起こしを取り直す
  await request.patch(`${API}/api/segments/${segments[0].id}`, {
    data: { text: '手で直した字幕です' },
  })
  await page.reload()
  await expect(overlay).toHaveAttribute('alt', '手で直した字幕です')
  expect(before).not.toBe('手で直した字幕です')
})
