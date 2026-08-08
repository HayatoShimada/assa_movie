import { expect, test } from '@playwright/test'
import { API, reset } from './helpers'

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
  // 既定値から始めたいので必ずリセットする。seedを直に叩くと、前のspecが
  // 変えたグローバル設定を引き継いでしまう
  await reset(request)
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto(`/#/media/${seed.media_id}`)
  await page.getByRole('button', { name: '設定' }).click()

  const select = page.getByTestId('setting-asr-model')
  await expect(select).toHaveValue('large-v3')
  await select.selectOption('large-v3-turbo')

  // 標準語化の注意書きが表示される
  await expect(page.getByText(/標準語化/)).toBeVisible()

  // 保存するまでは下書き。保存ボタンで確定する
  await expect(page.getByTestId('settings-save-status')).toHaveText('未保存の変更があります')
  await page.getByTestId('settings-save').click()
  await expect(page.getByTestId('settings-save-status')).toHaveText('保存しました')

  // リロードしても保持されている(バックエンドに保存された)
  await page.reload()
  await page.getByRole('button', { name: '設定' }).click()
  await expect(page.getByTestId('setting-asr-model')).toHaveValue('large-v3-turbo')

  // 後片付け
  await request.patch(`${API}/api/settings`, { data: { asr_model: 'large-v3' } })
})

test('設定タブで字幕サイズを調整すると保存される', async ({ page, request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto(`/#/media/${seed.media_id}`)
  await page.getByRole('button', { name: '設定' }).click()

  const slider = page.getByTestId('setting-subtitle-font-size')
  await slider.fill('62')
  await slider.dispatchEvent('mouseup')
  await page.getByTestId('settings-save').click()

  await expect
    .poll(async () => {
      const settings = await (await request.get(`${API}/api/settings`)).json()
      return settings.values.subtitle_font_size
    })
    .toBe(62)

  await page.reload()
  await page.getByRole('button', { name: '設定' }).click()
  await expect(page.getByText('字幕サイズ: 62px')).toBeVisible()

  // 後片付け
  await request.patch(`${API}/api/settings`, { data: { subtitle_font_size: 48 } })
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

test('エディタ: 境界バーのドラッグで動画とパネルの幅を変えられる', async ({ page, request }) => {
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.setViewportSize({ width: 1500, height: 900 })
  await page.goto(`/#/media/${seed.media_id}`)

  const handle = page.getByTestId('split-handle')
  await expect(handle).toBeVisible()
  const panelWidth = async () => (await page.locator('aside').boundingBox())!.width
  const before = await panelWidth()

  // 境界を左へ動かすとパネルが広がる
  const box = (await handle.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + 200)
  await page.mouse.down()
  await page.mouse.move(box.x - 250, box.y + 200, { steps: 10 })
  await page.mouse.up()
  await expect.poll(panelWidth).toBeGreaterThan(before + 100)

  // ダブルクリックで既定に戻る
  await handle.dblclick()
  await expect.poll(panelWidth).toBeCloseTo(before, -1)
})
