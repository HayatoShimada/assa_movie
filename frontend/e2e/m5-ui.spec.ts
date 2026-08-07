import { expect, test } from '@playwright/test'

const API = 'http://localhost:8001'

/** M5: ホーム画面 → 文字起こし → エディタ の画面操作テスト */
test.beforeEach(async ({ request }) => {
  await request.post(`${API}/api/e2e/reset`)
})

test('プロジェクトを作成して一覧に表示される', async ({ page }) => {
  await page.goto('/#/')
  await page.getByTestId('new-project-name').fill('新しい対談企画')
  await page.getByRole('button', { name: '作成' }).click()
  await expect(page.getByRole('heading', { name: '新しい対談企画' })).toBeVisible()
})

test('文字起こしを実行すると進捗が出て完了する', async ({ page, request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto('/#/')

  const row = page.getByTestId(`media-${seed.media_id}`)
  await expect(row).toBeVisible()

  // Fakeジョブを直接使う(実GPUを使わない)
  await request.post(`${API}/api/media/${seed.media_id}/jobs`, {
    data: { type: 'transcribe_fake', params: {} },
  })

  await expect
    .poll(
      async () =>
        (await (await request.get(`${API}/api/media/${seed.media_id}`)).json()).status,
      { timeout: 15000 },
    )
    .toBe('transcribed')

  await page.reload()
  await expect(row.getByRole('button', { name: '開く' })).toBeEnabled()
})

test('エディタでセグメントが表示されクリックで選択できる', async ({ page, request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await request.post(`${API}/api/media/${seed.media_id}/jobs`, {
    data: { type: 'transcribe_fake', params: {} },
  })
  await expect
    .poll(
      async () =>
        (await (await request.get(`${API}/api/media/${seed.media_id}`)).json()).status,
      { timeout: 15000 },
    )
    .toBe('transcribed')

  await page.goto(`/#/media/${seed.media_id}`)

  // セグメントが並ぶ(シードデータは4件)
  await expect(page.getByTestId('segment-0')).toContainText('去年ハッカソンに出たんですよ')
  await expect(page.getByTestId('segment-3')).toContainText('うん')

  // 相槌はグレー表示
  await expect(page.getByTestId('segment-3')).toHaveClass(/opacity-40/)

  // 相槌を非表示にすると消える
  await page.getByLabel('相槌を表示').uncheck()
  await expect(page.getByTestId('segment-3')).not.toBeAttached()
  await page.getByLabel('相槌を表示').check()

  // クリックで選択リングが付く
  await page.getByTestId('segment-1').click()
  await expect(page.getByTestId('segment-1')).toHaveClass(/ring-1/)
})

test('設定タブでASRモデルを切り替えると保存される', async ({ page, request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto(`/#/media/${seed.media_id}`)
  await page.getByRole('button', { name: '設定' }).click()

  const select = page.getByTestId('setting-asr-model')
  await expect(select).toHaveValue('large-v3')
  await select.selectOption('large-v3-turbo')

  // 標準語化の注意書きが表示される
  await expect(page.getByText(/標準語化/)).toBeVisible()

  // リロードしても保持されている(バックエンドに保存された)
  await page.reload()
  await page.getByRole('button', { name: '設定' }).click()
  await expect(page.getByTestId('setting-asr-model')).toHaveValue('large-v3-turbo')

  // 後片付け
  await request.patch(`${API}/api/settings`, { data: { asr_model: 'large-v3' } })
})

test('LLMプロバイダにGeminiが表示される(キー未設定なら選択不可)', async ({ page, request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto(`/#/media/${seed.media_id}`)
  await page.getByRole('button', { name: '設定' }).click()

  const gemini = page.getByTestId('setting-llm-provider').locator('option[value=gemini]')
  await expect(gemini).toBeAttached()

  const settings = await (await request.get(`${API}/api/settings`)).json()
  const ready = settings.llm_providers.find((p: { id: string }) => p.id === 'gemini').ready
  if (!ready) {
    // toBeDisabled() は <option> 要素では期待通り動かないため、DOMプロパティで検証する
    await expect(gemini).toHaveJSProperty('disabled', true)
    await expect(gemini).toContainText('APIキー未設定')
  }
})
