import { expect, test, type APIRequestContext } from '@playwright/test'

const API = 'http://localhost:8001'

/** M6: レビューUI・質問キュー・対話アシストの画面操作テスト */

async function seedTranscribed(request: APIRequestContext): Promise<number> {
  await request.post(`${API}/api/e2e/reset`)
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await request.post(`${API}/api/media/${seed.media_id}/jobs`, {
    data: { type: 'transcribe_fake', params: {} },
  })
  await expect
    .poll(
      async () => (await (await request.get(`${API}/api/media/${seed.media_id}`)).json()).status,
      { timeout: 15000 },
    )
    .toBe('transcribed')
  return seed.media_id
}

test('レビュー: 解決実行→提案が並び、承認でトランスクリプトに下線付き反映', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)

  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()

  // FakeLLMは「それ→去年のハッカソン」をreviewで1件提案する
  const row = page.locator('[data-testid^="review-"]')
  await expect(row).toHaveCount(1, { timeout: 15000 })
  await expect(row).toContainText('それ')
  await expect(row).toContainText('去年のハッカソン')

  // レビュータブのバッジが1になる
  await expect(page.getByTestId('tab-review')).toContainText('1')

  await row.getByRole('button', { name: '承認 (a)' }).click()
  await expect(page.locator('[data-testid^="applied-"]')).toHaveCount(1)

  // トランスクリプトに注釈形式で反映され、下線+原文ツールチップが付く
  await page.getByTestId('tab-transcript').click()
  const seg = page.getByTestId('segment-1')
  await expect(seg).toContainText('それ(去年のハッカソン)')
  const underlined = seg.locator('span[title^="原文:"]')
  await expect(underlined).toBeVisible()
})

test('レビュー: 却下するとfeedbackに残り適用されない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()

  const row = page.locator('[data-testid^="review-"]')
  await expect(row).toHaveCount(1, { timeout: 15000 })
  await row.getByRole('button', { name: '却下 (x)' }).click()

  await expect(page.getByText('レビュー待ちはありません')).toBeVisible()
  await page.getByTestId('tab-transcript').click()
  await expect(page.getByTestId('segment-1')).not.toContainText('去年のハッカソン')

  const edits = await (await request.get(`${API}/api/media/${mediaId}/edits?status=rejected`)).json()
  expect(edits).toHaveLength(1)
})

test('レビュー: キーボード(a)で承認できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()
  await expect(page.locator('[data-testid^="review-"]')).toHaveCount(1, { timeout: 15000 })

  await page.keyboard.press('a')
  await expect(page.locator('[data-testid^="applied-"]')).toHaveCount(1)
})

test('レビュー: 追加指示を「今後も使う」で保存して再実行できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-review').click()

  await page.getByPlaceholder(/追加指示/).fill('『あれ』はAIハッカソンを指す')
  await page.getByLabel('今後も使う').check()
  await page.getByTestId('run-resolve').click()
  await expect(page.locator('[data-testid^="review-"]')).toHaveCount(1, { timeout: 15000 })

  // プロジェクトのカスタム指示として保存されている
  const media = await (await request.get(`${API}/api/media/${mediaId}`)).json()
  const instructions = await (
    await request.get(`${API}/api/projects/${media.project_id}/instructions`)
  ).json()
  expect(instructions.map((i: { text: string }) => i.text)).toContain(
    '『あれ』はAIハッカソンを指す',
  )
})

test('質問: スキャン→候補ボタンで回答→全出現箇所が修正される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-questions').click()

  await page.getByTestId('run-scan').click()
  const card = page.locator('[data-testid^="question-"]')
  await expect(card).toHaveCount(1, { timeout: 15000 })
  await expect(card).toContainText('反動体')

  // 質問タブのバッジが付く
  await expect(page.getByTestId('tab-questions')).toContainText('1')

  await card.getByRole('button', { name: '半導体', exact: true }).click()
  await expect(page.getByText(/箇所を修正し、用語集に登録しました/)).toBeVisible()

  await page.getByTestId('tab-transcript').click()
  await expect(page.getByTestId('segment-2')).toContainText('半導体の話も面白かったです')
})

test('アシスト: セグメント選択→指示→提案を承認、指示昇格もできる', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)

  // 「反動体」を含むセグメントを選択するとチャット欄が出る
  await page.getByTestId('segment-2').click()
  await expect(page.getByTestId('assist-chat')).toBeVisible()

  await page.getByTestId('assist-input').fill('反動体は半導体の誤認識です')
  await page.getByRole('button', { name: '送信' }).click()

  const response = page.getByTestId('assist-response')
  await expect(response).toBeVisible({ timeout: 15000 })
  await expect(response).toContainText('半導体')

  // 提案を承認するとトランスクリプトに反映される(annotate形式)
  await response.getByRole('button', { name: '承認' }).click()
  await expect(page.getByTestId('segment-2')).toContainText('反動体(半導体)')

  // もう一度指示して、今度はカスタム指示への昇格を確認
  await page.getByTestId('assist-input').fill('今後も同じ解釈で')
  await page.getByRole('button', { name: '送信' }).click()
  await expect(page.getByTestId('assist-response')).toBeVisible({ timeout: 15000 })
  const promoteBtn = page.getByRole('button', { name: 'カスタム指示に追加' })
  if (await promoteBtn.isVisible()) {
    await promoteBtn.click()
    await expect(page.getByText('カスタム指示に追加しました')).toBeVisible()
    const media = await (await request.get(`${API}/api/media/${mediaId}`)).json()
    const instructions = await (
      await request.get(`${API}/api/projects/${media.project_id}/instructions`)
    ).json()
    expect(instructions.length).toBeGreaterThan(0)
  }
})
