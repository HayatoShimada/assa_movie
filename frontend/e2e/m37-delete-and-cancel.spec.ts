/**
 * M37: プロジェクトの削除と、文字起こしの中止。
 *
 * 削除の確認は window.confirm を使わない。webviewによって出方が変わり、
 * Tauriのデスクトップ版で押しても何も起きない事象があった。画面内で確認する。
 *
 * 文字起こしは数十分かかることがあるので、始めたあと止められる必要がある。
 */
import { expect, test } from '@playwright/test'
import { API, reset, seed } from './helpers'

test('プロジェクトを削除できる(確認は画面内で行う)', async ({ page, request }) => {
  const { project_id } = await seed(request)
  await page.goto('/')

  // いきなり消さない。確認を挟む
  await page.getByTestId(`project-delete-${project_id}`).click()
  await expect(page.getByTestId(`project-delete-confirm-${project_id}`)).toBeVisible()

  await page.getByTestId(`project-delete-confirm-${project_id}`).click()

  // 一覧から消える
  await expect(page.getByTestId(`project-delete-${project_id}`)).toBeHidden()
  // APIから見ても消えている(画面だけ消えたのではない)
  const projects = await (await request.get(`${API}/api/projects`)).json()
  expect(projects.some((p: { id: number }) => p.id === project_id)).toBe(false)
})

test('削除をやめれば残る', async ({ page, request }) => {
  const { project_id } = await seed(request)
  await page.goto('/')

  await page.getByTestId(`project-delete-${project_id}`).click()
  await page.getByRole('button', { name: 'やめる' }).click()

  await expect(page.getByTestId(`project-delete-${project_id}`)).toBeVisible()
  const projects = await (await request.get(`${API}/api/projects`)).json()
  expect(projects.some((p: { id: number }) => p.id === project_id)).toBe(true)
})

test('文字起こしを中止できる', async ({ page, request }) => {
  const { media_id } = await seed(request)
  await page.goto('/')

  await page.getByTestId(`media-transcribe-${media_id}`).click()
  // 実行中は中止ボタンが出る
  const cancelButton = page.getByTestId(`media-cancel-${media_id}`)
  await expect(cancelButton).toBeVisible()

  await cancelButton.click()
  await expect(cancelButton).toBeHidden()
})

test('中止したジョブはcancelledになり、失敗扱いにしない', async ({ request }) => {
  await reset(request)
  const { media_id } = await (await request.post(`${API}/api/e2e/seed`)).json()
  const job = await (
    await request.post(`${API}/api/media/${media_id}/jobs`, {
      data: { type: 'transcribe', params: {} },
    })
  ).json()

  await request.post(`${API}/api/jobs/${job.id}/cancel`)

  await expect
    .poll(async () => (await (await request.get(`${API}/api/jobs/${job.id}`)).json()).status, {
      timeout: 10000,
    })
    .toBe('cancelled')
  // 中止に失敗理由を残さない(利用者の操作であって異常ではない)
  const done = await (await request.get(`${API}/api/jobs/${job.id}`)).json()
  expect(done.error).toBeFalsy()
})

test('終わったジョブを中止しても壊れない', async ({ request }) => {
  await reset(request)
  const { media_id } = await (await request.post(`${API}/api/e2e/seed`)).json()
  const job = await (
    await request.post(`${API}/api/media/${media_id}/jobs`, {
      data: { type: 'transcribe', params: {} },
    })
  ).json()

  await expect
    .poll(async () => (await (await request.get(`${API}/api/jobs/${job.id}`)).json()).status, {
      timeout: 15000,
    })
    .toBe('completed')

  const res = await request.post(`${API}/api/jobs/${job.id}/cancel`)
  expect(res.status()).toBe(200)
  expect((await res.json()).status).toBe('completed')
})

test('実行中のジョブごとプロジェクトを削除できる', async ({ request }) => {
  await reset(request)
  const { project_id, media_id } = await (await request.post(`${API}/api/e2e/seed`)).json()
  const job = await (
    await request.post(`${API}/api/media/${media_id}/jobs`, {
      data: { type: 'transcribe', params: {} },
    })
  ).json()

  const res = await request.delete(`${API}/api/projects/${project_id}`)
  expect(res.status()).toBe(200)

  const projects = await (await request.get(`${API}/api/projects`)).json()
  expect(projects.some((p: { id: number }) => p.id === project_id)).toBe(false)
  // ジョブはメディアごと消える(参照が残らない)
  expect((await request.get(`${API}/api/jobs/${job.id}`)).status()).toBe(404)
})
