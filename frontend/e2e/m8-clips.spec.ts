import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

test('クリップ: 候補生成→カード表示→編集モード', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()

  await page.getByTestId('run-suggest').click()
  await expect(page.getByText('ハッカソンの話')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('完結した話題')).toBeVisible()

  // カードをクリックすると編集モードが開く
  await page.getByText('ハッカソンの話').click()
  await expect(page.getByTestId('clip-timeline')).toBeVisible()
  await expect(page.getByTestId('clip-duration')).toBeVisible()
  await expect(page.getByTestId('handle-start')).toBeVisible()
})

test('クリップ: 中抜き提案がタイムラインに出てクリックで切替できる', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  // シードの相槌セグメントを含む範囲でクリップを直接作る
  const clip = await (
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 8, title: '手動' },
    })
  ).json()

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('手動').click()

  await page.getByRole('button', { name: '中抜きを提案' }).click()
  const cut = page.locator('[data-testid^="cut-"]').first()
  await expect(cut).toBeVisible({ timeout: 10000 })

  const before = await page.getByTestId('clip-duration').textContent()
  await cut.click() // 中抜きOFF
  await expect(page.getByTestId('clip-duration')).not.toHaveText(before!)

  const cuts = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
  expect(cuts.find((c: { id: number }) => c.id === clip.id).cuts[0].active).toBe(0)
})

test('クリップ: メタ生成でフック案が出て選択できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/media/${mediaId}/clips`, {
    data: { start: 0, end: 8, title: 'メタ対象' },
  })
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('メタ対象').click()

  await page.getByRole('button', { name: 'タイトル・メタ生成' }).click()
  await expect(page.getByText('AIと古着の出会い')).toBeVisible({ timeout: 15000 })

  await page.getByRole('button', { name: 'AIと古着の出会い' }).click()
  await expect
    .poll(async () => {
      const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
      return clips[0].hook_text
    })
    .toBe('AIと古着の出会い')
})

test('クリップ: 自己完結化でresolveジョブが走り提案がレビューに入る', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/media/${mediaId}/clips`, {
    data: { start: 0, end: 8, title: '自己完結' },
  })
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('自己完結').click()

  await page.getByRole('button', { name: '指示語を自己完結化' }).click()
  await expect(page.getByText(/自己完結化完了/)).toBeVisible({ timeout: 15000 })

  // FakeLLMの提案(review)がレビュータブのバッジに乗る
  await expect(page.getByTestId('tab-review')).toContainText('1')
})

test('クリップ: 字幕位置を変更して保存できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  const clip = await (
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 8, title: '字幕位置テスト' },
    })
  ).json()

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('字幕位置テスト').click()

  await page.getByTestId('clip-subtitle-position').selectOption('top')
  await page.getByTestId('clip-subtitle-offset').fill('-30')
  await expect
    .poll(async () => {
      const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
      const target = clips.find((c: { id: number }) => c.id === clip.id)
      return `${target.subtitle_position}:${target.subtitle_offset_y}`
    })
    .toBe('top:-30')
})

test('クリップ: 個別の削除ボタンでそのクリップだけ消える', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  for (const title of ['消すクリップ', '残すクリップ']) {
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 5, title },
    })
  }

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await expect(page.getByText('消すクリップ')).toBeVisible()

  // 削除は独立したボタン(カードの選択とは別)
  const clips0 = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
  const doomed = clips0.find((c: { title: string }) => c.title === '消すクリップ')
  await page.getByTestId(`clip-delete-${doomed.id}`).click()

  await expect(page.getByText('消すクリップ')).toHaveCount(0)
  await expect(page.getByText('残すクリップ')).toBeVisible()
  const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
  expect(clips.map((c: { title: string }) => c.title)).toEqual(['残すクリップ'])
})

test('クリップ: 上下微調整がプレビューに即反映される(中央配置でも)', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/media/${mediaId}/clips`, {
    data: { start: 0, end: 8, title: 'オフセット反映テスト' },
  })

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('オフセット反映テスト').click()

  // 再生位置0秒の字幕が出ている状態で、スライダーを動かして位置が動くか見る
  const overlay = page.getByTestId('subtitle-overlay')
  await expect(overlay).toBeVisible()
  const topOf = async () => (await overlay.boundingBox())!.y

  for (const position of ['bottom', 'center'] as const) {
    await page.getByTestId('clip-subtitle-position').selectOption(position)
    await page.getByTestId('clip-subtitle-offset').fill('-100')
    await expect(page.getByTestId('clip-subtitle-offset')).toHaveValue('-100')
    const up = await topOf()

    await page.getByTestId('clip-subtitle-offset').fill('100')
    await expect(page.getByTestId('clip-subtitle-offset')).toHaveValue('100')
    const down = await topOf()

    // +は下方向。中央配置でもオフセットが効く(書き出しでは \pos で表現)
    expect(down, `位置=${position} でプレビューが動いていない`).toBeGreaterThan(up)
  }
})

test('クリップ: 全体設定で上書きボタンが効く', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  const clip = await (
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 8, title: '上書きテスト' },
    })
  ).json()

  await request.patch(`${API}/api/settings`, {
    data: { subtitle_position: 'top', subtitle_offset_y: -20 },
  })

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('上書きテスト').click()

  await page.getByRole('button', { name: '全体設定で上書き' }).click()

  await expect
    .poll(async () => {
      const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
      const target = clips.find((c: { id: number }) => c.id === clip.id)
      return `${target.subtitle_position}:${target.subtitle_offset_y}`
    })
    .toBe('top:-20')

  await request.patch(`${API}/api/settings`, {
    data: { subtitle_position: 'bottom', subtitle_offset_y: 0 },
  })
})
