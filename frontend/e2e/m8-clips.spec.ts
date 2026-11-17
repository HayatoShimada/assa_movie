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

  // 再生位置0秒の字幕が出ている状態で、位置とずらしを変えて字幕が描き直されるか見る。
  // 字幕は書き出しと同じ libass で描いた画像(E2Eでは透明な画像に差し替え)。
  // どの画像かは data-key(見た目から決まる)で分かる。実際に上下へ動くことは
  // tests/pipeline/test_subtitle_preview.py が画素で確かめている
  const overlay = page.getByTestId('subtitle-overlay')
  await expect(overlay).toBeVisible()
  // このクリップの位置・ずらし・範囲で描いた画像になっている(APIの答えと同じキー)
  const expectKey = async (position: string, offset: number) => {
    const preview = await (
      await request.get(
        `${API}/api/media/${mediaId}/subtitle-preview?position=${position}&offset_y=${offset}&start=0&end=8`,
      )
    ).json()
    await expect(overlay).toHaveAttribute('data-key', preview.events[0].key)
    return preview.events[0].key as string
  }

  const seen = new Set<string>()
  for (const position of ['bottom', 'center'] as const) {
    await page.getByTestId('clip-subtitle-position').selectOption(position)
    await page.getByTestId('clip-subtitle-offset').fill('-100')
    await expect(page.getByTestId('clip-subtitle-offset')).toHaveValue('-100')
    const up = await expectKey(position, -100)

    await page.getByTestId('clip-subtitle-offset').fill('100')
    await expect(page.getByTestId('clip-subtitle-offset')).toHaveValue('100')
    const down = await expectKey(position, 100)

    // 中央配置でもオフセットが効く(書き出しでは \pos で表現)
    expect(down, `位置=${position} でプレビューが変わっていない`).not.toBe(up)
    seen.add(up).add(down)
  }
  expect(seen.size, '位置×ずらしの4通りがすべて別の見た目').toBe(4)
  // 画像は実際に読み込めている
  await expect
    .poll(() => overlay.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0)
})

test('クリップ: 「既定の位置に戻す」でプロジェクト(未設定なら全体)の字幕位置に戻る', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  const clip = await (
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 8, title: '戻すテスト' },
    })
  ).json()
  // クリップだけ動かしておく
  await request.patch(`${API}/api/clips/${clip.id}`, {
    data: { subtitle_position: 'center', subtitle_offset_y: 50 },
  })
  await request.patch(`${API}/api/settings`, {
    data: { subtitle_position: 'top', subtitle_offset_y: -20 },
  })

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('戻すテスト').click()

  const reset = page.getByTestId('clip-subtitle-reset')
  // 戻す先が書いてある(「全体設定で上書き」は向きが読めなかった)
  await expect(reset).toHaveText('既定の位置に戻す(上・-20px)')
  await reset.click()

  const positionOf = async () => {
    const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
    const target = clips.find((c: { id: number }) => c.id === clip.id)
    return `${target.subtitle_position}:${target.subtitle_offset_y}`
  }
  await expect.poll(positionOf).toBe('top:-20')
  // 既に既定と同じなら押せない
  await expect(reset).toBeDisabled()

  // プロジェクトで上書きしていれば、そちらが戻す先になる(3層設定)
  const media = await (await request.get(`${API}/api/media/${mediaId}`)).json()
  await request.patch(`${API}/api/projects/${media.project_id}`, {
    data: { settings: { subtitle_position: 'center', subtitle_offset_y: 10 } },
  })
  await page.reload()
  await page.getByTestId('tab-clips').click()
  await page.getByText('戻すテスト').click()
  await expect(reset).toHaveText('既定の位置に戻す(中央・10px)')
  await reset.click()
  await expect.poll(positionOf).toBe('center:10')

  await request.patch(`${API}/api/settings`, {
    data: { subtitle_position: 'bottom', subtitle_offset_y: 0 },
  })
})
