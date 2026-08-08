/**
 * M33: 初回セットアップのウィザード。
 *
 * インストール版の利用者は設定タブのどこに何があるか知らない。
 * 初回だけ1本道で案内し、済ませたら二度と出さない。
 * ここで決めたことは設定タブから変えられる(同じAPIを使っているため)。
 */
import { expect, test } from '@playwright/test'
import { API, reset, seedTranscribed } from './helpers'

/** 初回起動の状態に戻す(E2Eサーバーは既定で「済ませた」状態) */
async function asFirstRun(request) {
  // 登録済みのAPIキーも消す。前のspecの結果に引きずられないように
  await reset(request)
  await request.patch(`${API}/api/settings`, { data: { setup_completed: false } })
}

test('初回はウィザードが出て、最後まで進むと閉じる', async ({ page, request }) => {
  await asFirstRun(request)
  await page.goto('/')

  const wizard = page.getByTestId('setup-wizard')
  await expect(wizard).toBeVisible()

  // 1. 環境: この機体の構成が出て、推奨をそのまま当てられる
  await expect(page.getByTestId('wizard-env')).toBeVisible()
  await page.getByTestId('wizard-apply-recommended').click()
  await expect(page.getByTestId('wizard-apply-recommended')).toHaveText('適用しました')
  await page.getByTestId('wizard-next').click()

  // 2. AI: クラウドが先に並ぶ(Ollamaは別途の導入が要るため)
  const provider = page.getByTestId('wizard-llm-provider')
  await expect(provider).toBeVisible()
  await expect(provider.locator('option').first()).not.toHaveAttribute('value', 'ollama')
  await page.getByTestId('wizard-next').click()

  // 3. 追加モデル: 取得の導線が出る
  await expect(page.getByTestId('wizard-models')).toBeVisible()
  await page.getByTestId('wizard-next').click()

  // 4. 完了
  await expect(page.getByTestId('wizard-done-text')).toBeVisible()
  await page.getByTestId('wizard-next').click()

  await expect(wizard).toBeHidden()
  // 記録されるので、開き直しても出ない
  await page.reload()
  await expect(page.getByTestId('setup-wizard')).toBeHidden()
})

test('ウィザードでAPIキーを登録できる', async ({ page, request }) => {
  await asFirstRun(request)
  await page.goto('/')
  await page.getByTestId('wizard-next').click() // 環境 → AI

  await page.getByTestId('wizard-llm-provider').selectOption('claude')
  await page.getByTestId('wizard-key-input').fill('sk-ant-api03-e2etestkey')
  await page.getByTestId('wizard-key-save').click()

  await expect(page.getByTestId('wizard-key-ready')).toContainText('登録済み')
  // APIから見ても登録されている = 設定タブと同じ場所に入っている
  const keys = await (await request.get(`${API}/api/keys`)).json()
  expect(keys.claude.configured).toBe(true)
})

test('不正なキーはエラーになり、登録されない', async ({ page, request }) => {
  await asFirstRun(request)
  await page.goto('/')
  await page.getByTestId('wizard-next').click()

  await page.getByTestId('wizard-llm-provider').selectOption('claude')
  await page.getByTestId('wizard-key-input').fill('でたらめなキー')
  await page.getByTestId('wizard-key-save').click()

  await expect(page.getByTestId('wizard-key-error')).toBeVisible()
  const keys = await (await request.get(`${API}/api/keys`)).json()
  expect(keys.claude.configured).toBe(false)
})

test('「あとで設定する」で閉じられ、再度出てこない', async ({ page, request }) => {
  await asFirstRun(request)
  await page.goto('/')

  await page.getByTestId('wizard-skip').click()

  await expect(page.getByTestId('setup-wizard')).toBeHidden()
  await page.reload()
  await expect(page.getByTestId('setup-wizard')).toBeHidden()
})

test('設定タブからやり直せる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  // 済ませた状態なので出ていない
  await expect(page.getByTestId('setup-wizard')).toBeHidden()

  await page.getByTestId('rerun-setup').click()

  await expect(page.getByTestId('setup-wizard')).toBeVisible()
})
