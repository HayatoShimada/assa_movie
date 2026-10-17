/**
 * M41: 名前・用語の辞書(利用者単位・全プロジェクト共通)。
 *
 * 質問タブで答えた固有名詞の正しい表記を覚え、次の文字起こしでWhisperに渡す。
 * 設定タブの「名前・用語の辞書」で見て・足して・直して・消せる。
 */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

async function openDictionary(page, mediaId: number) {
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  await expect(page.getByTestId('user-terms-panel')).toBeVisible()
  return page.getByTestId('user-terms-panel')
}

test('辞書: 質問に答えると辞書に載り、以前の聞き間違いも表示される', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-questions').click()
  await page.getByTestId('run-scan').click()
  const card = page.locator('[data-testid^="question-"]')
  await expect(card).toHaveCount(1, { timeout: 15000 })

  await card.getByRole('button', { name: '半導体', exact: true }).click()
  await expect(
    page.getByText('「半導体」を辞書に覚えました(次の文字起こしから使います)'),
  ).toBeVisible()

  await page.getByTestId('tab-settings').click()
  const row = page.locator('[data-testid^="user-term-row-"]')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('半導体')
  await expect(row).toContainText('以前の聞き間違い: 反動体')

  // 辞書は全プロジェクト共通(APIでもプロジェクトに紐づかない場所にある)
  const terms = await (await request.get(`${API}/api/user-terms`)).json()
  expect(terms.map((t: { term: string }) => t.term)).toEqual(['半導体'])
})

test('辞書: 設定タブで追加・修正・削除できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  const panel = await openDictionary(page, mediaId)
  await expect(page.getByTestId('user-terms-empty')).toBeVisible()

  // 追加
  await page.getByTestId('user-term-input').fill('反動体')
  await page.getByTestId('user-term-add').click()
  const row = panel.locator('[data-testid^="user-term-row-"]')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('反動体')
  await expect(page.getByTestId('user-term-input')).toHaveValue('')

  // 修正(表記と以前の聞き間違い)
  await row.getByRole('button', { name: '直す' }).click()
  await row.getByLabel('正しい表記').fill('半導体')
  await row.getByLabel('以前の聞き間違い').fill('反動体、はんどう体')
  await row.getByRole('button', { name: '保存' }).click()
  await expect(row).toContainText('半導体')
  await expect(row).toContainText('以前の聞き間違い: 反動体、はんどう体')

  const terms = await (await request.get(`${API}/api/user-terms`)).json()
  expect(terms).toHaveLength(1)
  expect(terms[0].term).toBe('半導体')
  expect(terms[0].misrecognitions).toEqual(['反動体', 'はんどう体'])

  // 削除
  await row.getByRole('button', { name: '削除' }).click()
  await expect(row).toHaveCount(0)
  await expect(page.getByTestId('user-terms-empty')).toBeVisible()
})

test('辞書: すでにある語に直そうとすると理由を表示する', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/user-terms`, { data: { term: '半導体' } })
  await request.post(`${API}/api/user-terms`, { data: { term: '反動体' } })
  const panel = await openDictionary(page, mediaId)

  // 編集中は語が入力欄の値になり本文から消えるので、行はIDで掴み直す
  const rowId = await panel
    .locator('[data-testid^="user-term-row-"]', { hasText: '反動体' })
    .getAttribute('data-testid')
  const row = page.getByTestId(rowId!)
  await row.getByRole('button', { name: '直す' }).click()
  await row.getByLabel('正しい表記').fill('半導体')
  await row.getByRole('button', { name: '保存' }).click()
  await expect(row).toContainText('「半導体」はすでに辞書にあります')
})

test('辞書: 使わない設定にすると辞書の画面でも分かる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openDictionary(page, mediaId)
  await expect(page.getByTestId('user-terms-disabled')).toHaveCount(0)

  await page.getByTestId('setting-asr-use-user-terms').uncheck()
  await page.getByTestId('settings-save').click()
  await expect(page.getByTestId('user-terms-disabled')).toBeVisible()

  const settings = await (await request.get(`${API}/api/settings`)).json()
  expect(settings.values.asr_use_user_terms).toBe(false)
})
