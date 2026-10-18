/**
 * M41: 初心者が迷わないための、ホームと文字起こしの手直し(v2.0)。
 *
 * - 全体の設定はホームから開ける(文字起こし前でも見直せる)
 * - プロジェクト名が空なら「作成」は押せず、理由を出す。テンプレートの説明を1行出す
 * - 誤認識を手で直せる(ダブルクリック/鉛筆)。直したものはいつでも戻せる
 * - 話者名を押すと名前を変えられる。行ごとの付け替えもできる
 * - 「AIに指示」の応答は、承認待ちであることをそのとおりに伝える
 */
import { expect, test } from '@playwright/test'
import { API, reset, seedTranscribed } from './helpers'

test('ホームの「全体の設定」から全体の設定を開き、戻れる', async ({ page, request }) => {
  await reset(request)
  await page.goto('/')
  await page.getByTestId('open-global-settings').click()

  await expect(page).toHaveURL(/#\/settings$/)
  const heading = page.getByTestId('global-settings-heading')
  await expect(heading).toContainText('全体の設定(すべてのプロジェクト共通)')
  await expect(heading).toContainText('各プロジェクトの「設定」で上書き')
  // 中身は編集画面の設定タブと同じフォーム
  await expect(page.getByTestId('rerun-setup-panel')).toBeVisible()

  await page.getByTestId('settings-back').click()
  await expect(page).toHaveURL(/#\/$/)
  await expect(page.getByTestId('new-project-name')).toBeVisible()
})

test('編集画面の設定タブも「全体の設定」だと分かる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  await expect(page.getByTestId('global-settings-heading')).toContainText(
    'すべてのプロジェクト共通',
  )
})

test('プロジェクト名が空なら「作成」は押せず、理由が出る', async ({ page, request }) => {
  await reset(request)
  await page.goto('/')
  await expect(page.getByTestId('create-project')).toBeDisabled()
  await expect(page.getByTestId('new-project-name-hint')).toContainText('プロジェクト名を入れると')

  await page.getByTestId('new-project-name').fill('対談')
  await expect(page.getByTestId('create-project')).toBeEnabled()
  await expect(page.getByTestId('new-project-name-hint')).toHaveCount(0)
})

test('テンプレートを選ぶと、何が起きるかが1行で出る', async ({ page, request }) => {
  await reset(request)
  await page.goto('/')
  const desc = page.getByTestId('template-description')
  await expect(desc).toContainText('そのまま横長')

  await page.getByTestId('template-l2p').click()
  // 既定の変換方式はぼかし背景
  await expect(desc).toContainText('縦長(1080×1920)の切り抜きを作ります')
  await expect(desc).toContainText('ぼかした映像で埋めます')
})

test('誤認識を手で直し、手直しを取り消せる(原文は残る)', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await expect(page.getByTestId('transcript-hint')).toContainText('ダブルクリック')

  const row = page.getByTestId('segment-2')
  await expect(row).toContainText('反動体の話も面白かったです')
  await row.dblclick()
  const input = page.getByTestId('segment-edit-input-2')
  await expect(input).toHaveValue('反動体の話も面白かったです')
  await input.fill('半導体の話も面白かったです')
  await input.press('Enter')

  await expect(page.getByTestId('segment-editor-2')).toHaveCount(0)
  await expect(row).toContainText('半導体の話も面白かったです')
  await expect(row).toContainText('(編集済)')
  // 原文はホバーで見える
  await expect(row.locator('span[title^="原文:"]')).toHaveAttribute('title', /反動体/)

  const segs = await (await request.get(`${API}/api/media/${mediaId}/segments`)).json()
  expect(segs[2].text).toBe('高田さん: 半導体の話も面白かったです')
  expect(segs[2].original_text).toBe('高田さん: 反動体の話も面白かったです')

  // 鉛筆ボタンからも開ける。「手直しを取り消す」で元に戻る
  await row.click()
  await page.getByTestId('segment-edit-2').click()
  await page.getByTestId('segment-restore-2').click()
  await expect(row).toContainText('反動体の話も面白かったです')
  await expect(row).not.toContainText('(編集済)')
})

test('話者名を押して名前を変え、行ごとに付け替えられる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)

  await page.getByTestId('speaker-0').click()
  await page.getByTestId('speaker-rename-input-0').fill('山田')
  await page.getByTestId('speaker-rename-save-0').click()

  // この動画の「はやまる」の行がすべて変わる
  await expect(page.getByTestId('speaker-0')).toHaveText('山田')
  await expect(page.getByTestId('speaker-1')).toHaveText('山田')
  await expect(page.getByTestId('speaker-2')).toHaveText('高田さん')

  // 既にいる話者の名前にはできない(2人が混ざって戻せなくなる)
  await page.getByTestId('speaker-0').click()
  await page.getByTestId('speaker-rename-input-0').fill('高田さん')
  await page.getByTestId('speaker-rename-save-0').click()
  await expect(page.getByTestId('speaker-menu-0')).toContainText('すでにこの動画にいる話者')

  // この行だけ別の話者に
  await page.getByTestId('speaker-assign-0-高田さん').click()
  await expect(page.getByTestId('speaker-0')).toHaveText('高田さん')
  await expect(page.getByTestId('speaker-1')).toHaveText('山田')
})

test('AIに指示: 応答は「案を作った・承認で反映」と状態どおりに伝える', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('segment-2').click()
  await page.getByTestId('assist-input').fill('反動体は半導体の誤認識です')
  await page.getByRole('button', { name: '送信' }).click()

  const reply = page.getByTestId('assist-reply')
  await expect(reply).toContainText('案を作りました', { timeout: 15000 })
  await expect(reply).toContainText('まだ反映していません')
  const response = page.getByTestId('assist-response')
  await expect(response).toContainText('承認待ち')
  await expect(response).toContainText('承認すると: 反動体(半導体)の話も面白かったです')
  // 承認するまで行は変わらない
  await expect(page.getByTestId('segment-2')).not.toContainText('(半導体)')

  await response.getByRole('button', { name: '承認', exact: true }).click()
  await expect(response).toContainText('反映しました')
  await expect(page.getByTestId('segment-2')).toContainText('反動体(半導体)')
})
