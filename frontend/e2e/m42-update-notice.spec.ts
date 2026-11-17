/**
 * M42: 新しい版が出ていることを知らせる(issue #3)。
 *
 * アプリに自動更新は無い。報告者は v2.0.0 が出ていることに気付かず v1.0.1 を
 * 使い続け、既に改善済みの内容で困っていた。起動して最初に開くホームで知らせ、
 * ダウンロードページを開くボタンと入れ直しの手順を添える。
 *
 * E2EのバックエンドはGitHubへ行かない。「最新のリリース」は
 * /api/e2e/latest-release で仕込む(今の版は 2.0.0 に固定)。
 */
import { expect, test, type APIRequestContext } from '@playwright/test'
import { API, reset } from './helpers'

async function setLatest(request: APIRequestContext, release: Record<string, unknown>) {
  await request.post(`${API}/api/e2e/latest-release`, { data: release })
}

test('新しい版があればホームで知らせ、ダウンロードページを開ける', async ({ page, request }) => {
  await reset(request)
  await setLatest(request, {
    tag_name: 'v2.1.0',
    body: '### 直った不具合\n- 書き出した動画が見つからなかった',
  })
  await page.goto('/')

  const banner = page.getByTestId('update-banner')
  await expect(banner).toBeVisible()
  await expect(page.getByTestId('update-latest')).toHaveText('v2.1.0')
  await expect(banner).toContainText('お使いの版: v2.0.0')

  // 手順と変更点は畳んである(開くと、入れ直し方とデータが残ることが分かる)
  await banner.locator('summary').click()
  await expect(page.getByTestId('update-steps')).toContainText('そのまま残ります')
  await expect(page.getByTestId('update-steps')).toContainText('macOS')
  await expect(page.getByTestId('update-notes')).toContainText('書き出した動画が見つからなかった')

  // ダウンロードページはバックエンドが既定のブラウザで開く(決まったURLだけ)
  await page.getByTestId('update-open').click()
  await expect
    .poll(async () => (await request.get(`${API}/api/e2e/revealed`)).json())
    .toEqual(['https://github.com/HayatoShimada/assa_movie/releases/latest'])
})

test('「あとで」はその版だけ閉じる。さらに新しい版が出たらまた知らせる', async ({
  page,
  request,
}) => {
  await reset(request)
  await setLatest(request, { tag_name: 'v2.1.0', body: '' })
  await page.goto('/')
  await page.getByTestId('update-later').click()
  await expect(page.getByTestId('update-banner')).toHaveCount(0)

  await page.reload()
  await expect(page.getByTestId('open-global-settings')).toBeVisible()
  await expect(page.getByTestId('update-banner')).toHaveCount(0)

  await setLatest(request, { tag_name: 'v2.2.0', body: '' })
  await page.reload()
  await expect(page.getByTestId('update-latest')).toHaveText('v2.2.0')
})

test('最新の版ならホームには何も出さず、設定に今の版が出る', async ({ page, request }) => {
  await reset(request)
  await page.goto('/')
  await expect(page.getByTestId('open-global-settings')).toBeVisible()
  await expect(page.getByTestId('update-banner')).toHaveCount(0)

  await page.getByTestId('open-global-settings').click()
  await expect(page.getByTestId('about-version')).toHaveText('v2.0.0')
  await expect(page.getByTestId('about-update-status')).toHaveText('最新の版です')
})

test('起動時の確認は切れる。切っても「今すぐ確認」はできる', async ({ page, request }) => {
  await reset(request)
  await setLatest(request, { tag_name: 'v2.1.0', body: '' })
  await page.goto('/#/settings')
  await expect(page.getByTestId('about-update-status')).toContainText('新しい版 v2.1.0')

  await page.getByTestId('about-auto-check').uncheck()
  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values.update_check_enabled)
    .toBe(false)
  await expect(page.getByTestId('about-update-status')).toContainText('未確認')

  // 切っている間はホームにも出さない(尋ねていないので分からない)
  await page.goto('/')
  await expect(page.getByTestId('open-global-settings')).toBeVisible()
  await expect(page.getByTestId('update-banner')).toHaveCount(0)

  await page.goto('/#/settings')
  await page.getByTestId('about-check-now').click()
  await expect(page.getByTestId('about-update-status')).toContainText('新しい版 v2.1.0')
  await expect(page.getByTestId('about-open')).toBeVisible()
})
