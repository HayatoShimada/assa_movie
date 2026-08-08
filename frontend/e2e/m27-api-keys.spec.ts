/** M27: APIキーの登録とClaudeプロバイダの選択 */
import { expect, test } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

async function openSettings(page, mediaId: number) {
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  await expect(page.getByTestId('apikeys-panel')).toBeVisible()
}

test('APIキー: 未登録から登録して、キー本体は画面に出ない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  const panel = page.getByTestId('apikeys-panel')
  await expect(panel).toContainText('未登録')

  await page.getByTestId('apikey-input-claude').fill('sk-ant-api03-e2etestkey')
  await page.getByTestId('apikey-save-claude').click()

  await expect(panel).toContainText('登録済み …tkey')
  // 全文はどこにも出さない
  await expect(panel).not.toContainText('sk-ant-api03-e2etestkey')
  await expect(page.getByTestId('apikey-input-claude')).toHaveValue('')
})

test('APIキー: 形式が違うキーはエラーになり登録されない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  await page.getByTestId('apikey-input-claude').fill('でたらめなキー')
  await page.getByTestId('apikey-save-claude').click()

  await expect(page.getByTestId('apikey-error-claude')).toContainText('sk-ant-')
  await expect(page.getByTestId('apikeys-panel')).toContainText('未登録')
})

test('APIキー: 登録すると削除できる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  await page.getByTestId('apikey-input-claude').fill('sk-ant-api03-e2etestkey')
  await page.getByTestId('apikey-save-claude').click()
  await expect(page.getByTestId('apikeys-panel')).toContainText('登録済み')

  await page.getByTestId('apikey-delete-claude').click()
  await expect(page.getByTestId('apikeys-panel')).toContainText('未登録')
  expect((await (await request.get(`${API}/api/keys`)).json()).claude.configured).toBe(false)
})

test('LLMプロバイダ: Claudeはキーが無いと選べず、登録すると選べる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  const provider = page.getByTestId('setting-llm-provider')
  const claude = provider.locator('option[value="claude"]')
  await expect(claude).toHaveCount(1)
  // <option> の disabled はプロパティで見る(toBeDisabledはoptionを対象にしない)
  await expect(claude).toHaveJSProperty('disabled', true)

  await page.getByTestId('apikey-input-claude').fill('sk-ant-api03-e2etestkey')
  await page.getByTestId('apikey-save-claude').click()

  await expect(claude).toHaveJSProperty('disabled', false)
  await provider.selectOption('claude')
  await page.getByTestId('settings-save').click()
  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values.llm_provider)
    .toBe('claude')
})
