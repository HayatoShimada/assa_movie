/**
 * M40: ホームと編集画面の見せ方。
 *
 * - 動画の状態は日本語で出す(registered / transcribed をそのまま出していた)
 * - 次にやることだけを主ボタンにする(文字起こし前は「文字起こし」、済んだら「開く」)
 * - 再文字起こしは手直しとレビュー結果を消すので、確認を挟む
 * - クリップの状態も日本語で出す(suggested をそのまま出していた)
 */
import { expect, test } from '@playwright/test'
import { API, reset, seed, seedTranscribed } from './helpers'

test('プロジェクトが無いときは、何をすればよいかを案内する', async ({ page, request }) => {
  await reset(request)
  await page.goto('/')
  await expect(page.getByTestId('projects-empty')).toContainText('プロジェクト名')
})

test('文字起こし前の動画: 状態は日本語で、主ボタンは「文字起こし」', async ({ page, request }) => {
  const { media_id } = await seed(request)
  await page.goto('/')
  const row = page.getByTestId(`media-${media_id}`)

  await expect(row.getByTestId(`media-state-${media_id}`)).toHaveText('文字起こし前')
  await expect(row).not.toContainText('registered')
  // まだ開けないので「開く」は出さない(押せないボタンを並べて迷わせない)
  await expect(row.getByRole('button', { name: '開く' })).toHaveCount(0)
  await expect(row.getByTestId(`media-transcribe-${media_id}`)).toHaveText('文字起こし')
  // 文字起こし前は確認なしで始まる
  await row.getByTestId(`media-transcribe-${media_id}`).click()
  await expect(row.getByTestId(`media-state-${media_id}`)).toHaveText(
    /順番待ち|文字起こし中|文字起こし済み/,
  )
})

test('文字起こし済みの動画: 「開く」で編集画面へ。見出しにプロジェクト名と動画名', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto('/')
  const row = page.getByTestId(`media-${mediaId}`)

  await expect(row.getByTestId(`media-state-${mediaId}`)).toHaveText('文字起こし済み')
  await expect(row).not.toContainText('transcribed')
  await row.getByRole('button', { name: '開く' }).click()

  await expect(page).toHaveURL(new RegExp(`#/media/${mediaId}$`))
  const header = page.getByTestId('editor-header')
  await expect(header).toContainText('E2Eテスト対談')
  await expect(header).toContainText('sample.mov')

  await header.getByRole('button', { name: 'プロジェクト一覧' }).click()
  await expect(page.getByTestId(`media-${mediaId}`)).toBeVisible()
})

test('再文字起こしは確認してから始める(やめれば何も起きない)', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto('/')
  const row = page.getByTestId(`media-${mediaId}`)

  await row.getByTestId(`media-transcribe-${mediaId}`).click()
  const confirm = row.getByTestId(`media-retranscribe-confirm-${mediaId}`)
  await expect(confirm).toBeVisible()
  await expect(row).toContainText('レビュー結果')

  // やめる → ジョブは作られず、状態もそのまま
  await row.getByRole('button', { name: 'やめる' }).click()
  await expect(confirm).toBeHidden()
  await expect(row.getByTestId(`media-state-${mediaId}`)).toHaveText('文字起こし済み')

  // 確認して始める → 工程名つきの進捗が出る
  await row.getByTestId(`media-transcribe-${mediaId}`).click()
  await row.getByTestId(`media-retranscribe-confirm-${mediaId}`).click()
  await expect(row).toContainText('話者分離中', { timeout: 10000 })
  await expect(row).toContainText('文字起こし完了', { timeout: 15000 })
})

test('クリップの状態は日本語で出る', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/media/${mediaId}/clips`, {
    data: { start: 0, end: 6, title: '手で作ったクリップ' },
  })
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()

  const card = page.locator('[data-testid^="clip-"]').filter({ hasText: '手で作ったクリップ' })
  await expect(card).toContainText('自分で作成')
  await expect(card).not.toContainText('draft')
})
