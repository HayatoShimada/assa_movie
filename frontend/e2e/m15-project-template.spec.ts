/** M15: プロジェクトテンプレート・プロジェクト設定・削除・クリップの縦変換UI */
import { expect, test, type APIRequestContext } from '@playwright/test'

const API = 'http://localhost:8001'

async function reset(request: APIRequestContext) {
  await request.post(`${API}/api/e2e/reset`)
}

async function seedTranscribed(
  request: APIRequestContext,
  orientation: 'landscape' | 'portrait' = 'landscape',
): Promise<number> {
  await reset(request)
  const seed = await (
    await request.post(`${API}/api/e2e/seed?output_orientation=${orientation}`)
  ).json()
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

test('プロジェクト作成: テンプレート「横→縦」と設定の上書きが保存される', async ({
  page,
  request,
}) => {
  await reset(request)
  await page.goto('/')

  await page.getByTestId('new-project-name').fill('縦動画プロジェクト')
  await page.getByTestId('template-l2p').click()

  // 詳細設定を開いて変換方式を中央クロップに(差分だけ保存される)
  await page.getByTestId('toggle-project-settings').click()
  await page.getByTestId('new-project-convert-method').selectOption('crop')

  await page.getByTestId('create-project').click()
  await expect(page.getByText('縦動画プロジェクト')).toBeVisible()

  // APIで検証: テンプレートと設定差分が永続化されている
  const projects = await (await request.get(`${API}/api/projects`)).json()
  const created = projects.find(
    (p: { name: string }) => p.name === '縦動画プロジェクト',
  )
  expect(created.output_orientation).toBe('portrait')
  expect(created.input_orientation).toBe('landscape')
  expect(created.settings.convert_method).toBe('crop')
  // 変更していない項目は差分に入らない(グローバルに追従する)
  expect(created.settings.subtitle_font_size).toBeUndefined()

  // カードにテンプレートバッジが出る
  await expect(page.getByTestId(`project-template-badge-${created.id}`)).toHaveText('横 → 縦')
})

test('プロジェクト設定: 編集パネルで上書き→既定に戻す', async ({ page, request }) => {
  await reset(request)
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto('/')

  await page.getByTestId(`project-settings-${seed.project_id}`).click()
  await page
    .getByTestId(`project-${seed.project_id}-convert-method`)
    .selectOption('face')

  await expect
    .poll(async () => {
      const p = await (await request.get(`${API}/api/projects/${seed.project_id}`)).json()
      return p.settings.convert_method
    })
    .toBe('face')

  // 既定に戻すと差分から消える
  await page.getByRole('button', { name: '既定に戻す' }).click()
  await expect
    .poll(async () => {
      const p = await (await request.get(`${API}/api/projects/${seed.project_id}`)).json()
      return p.settings.convert_method ?? 'なし'
    })
    .toBe('なし')
})

test('プロジェクト削除: 確認ダイアログ→カードが消える', async ({ page, request }) => {
  await reset(request)
  const seed = await (await request.post(`${API}/api/e2e/seed`)).json()
  await page.goto('/')
  await expect(page.getByText('E2Eテスト対談')).toBeVisible()

  page.on('dialog', (d) => d.accept())
  await page.getByTestId(`project-delete-${seed.project_id}`).click()

  await expect(page.getByText('E2Eテスト対談')).not.toBeVisible()
  const projects = await (await request.get(`${API}/api/projects`)).json()
  expect(projects).toHaveLength(0)
})

test('クリップ: 縦プロジェクトでプレビューが縦になり、方式上書きとクロップ位置が保存される', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request, 'portrait')
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()

  // プレビュー枠が縦(9:16)になっている
  await expect(page.getByTestId('player-frame')).toHaveAttribute('data-orientation', 'portrait')

  // 候補を生成して編集モードへ
  await page.getByTestId('run-suggest').click()
  await expect(page.getByText('ハッカソンの話')).toBeVisible({ timeout: 15000 })
  await page.getByText('ハッカソンの話').click()

  // 変換方式をクロップに上書き → スライダが現れる
  await page.getByTestId('clip-convert-method').selectOption('crop')
  await expect(page.getByTestId('clip-crop-x')).toBeVisible()
  await page.getByTestId('clip-crop-x').fill('0.2')

  await expect
    .poll(async () => {
      const clips = await (await request.get(`${API}/api/media/${mediaId}/clips`)).json()
      return { method: clips[0].convert_method, cropX: clips[0].crop_x }
    })
    .toEqual({ method: 'crop', cropX: 0.2 })
})
