import { expect, test } from '@playwright/test'
import { API } from './helpers'

/**
 * 基盤の疎通確認。UI実装後はここに画面操作のテストを足していく。
 * バックエンドはFakeLLM+一時DBなので、GPUもOllamaも不要で通る。
 */
test.beforeEach(async ({ request }) => {
  await request.post(`${API}/api/e2e/reset`)
})

test('バックエンドが応答する', async ({ request }) => {
  const res = await request.get(`${API}/api/health`)
  expect(res.ok()).toBeTruthy()
  expect(await res.json()).toEqual({ status: 'ok' })
})

test('フロントが起動して表示される', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})

test('文字起こしから指示語レビューまでAPIが通る', async ({ request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  const mediaId = seed.media_id

  // 文字起こし(Fake)
  const job = await (
    await request.post(`${API}/api/media/${mediaId}/jobs`, {
      data: { type: 'transcribe_fake', params: {} },
    })
  ).json()

  await expect
    .poll(async () => (await (await request.get(`${API}/api/jobs/${job.id}`)).json()).status, {
      timeout: 15000,
    })
    .toBe('completed')

  const segments = await (await request.get(`${API}/api/media/${mediaId}/segments`)).json()
  expect(segments.length).toBeGreaterThan(0)
  expect(segments.some((s: { is_aizuchi: boolean }) => s.is_aizuchi)).toBeTruthy()

  // 指示語置換(FakeLLMが1件提案する)
  const resolveJob = await (
    await request.post(`${API}/api/media/${mediaId}/jobs`, {
      data: { type: 'resolve', params: { apply_mode: 'all_review' } },
    })
  ).json()
  await expect
    .poll(
      async () => (await (await request.get(`${API}/api/jobs/${resolveJob.id}`)).json()).status,
      { timeout: 15000 },
    )
    .toBe('completed')

  const edits = await (await request.get(`${API}/api/media/${mediaId}/edits`)).json()
  expect(edits).toHaveLength(1)
  expect(edits[0].status).toBe('proposed')

  // 承認するとセグメントに反映される
  await request.post(`${API}/api/edits/${edits[0].id}/accept`, { data: {} })
  const after = await (await request.get(`${API}/api/media/${mediaId}/segments`)).json()
  expect(after[1].text).toContain('去年のハッカソン')
})
