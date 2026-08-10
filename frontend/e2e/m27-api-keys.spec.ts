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

test('APIキー: Geminiの新形式(AQ.〜)も登録できる', async ({ page, request }) => {
  // 接頭辞(AIza〜)での形式チェックをやめ、疎通確認で判定するようになった
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  await page.getByTestId('apikey-input-gemini').fill('AQ.Ab8RN6Je2etestkey')
  await page.getByTestId('apikey-save-gemini').click()

  await expect(page.getByTestId('apikeys-panel')).toContainText('登録済み …tkey')
  expect((await (await request.get(`${API}/api/keys`)).json()).gemini.configured).toBe(true)
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

test('LLMセクションにキー登録の動線があり、その場で登録すると選べる', async ({ page, request }) => {
  // 「(APIキー未設定)」と出るだけでは、どこで登録するのか分からなかった
  const mediaId = await seedTranscribed(request)
  await openSettings(page, mediaId)

  const setup = page.getByTestId('llm-key-setup')
  await expect(setup).toBeVisible()

  const provider = page.getByTestId('setting-llm-provider')
  const gemini = provider.locator('option[value="gemini"]')
  await expect(gemini).toHaveJSProperty('disabled', true)

  await page.getByTestId('llmkey-input-gemini').fill('AQ.Ab8RN6Je2etestkey')
  await page.getByTestId('llmkey-save-gemini').click()

  await expect(gemini).toHaveJSProperty('disabled', false)
  // 選択していないプロバイダは、登録が済んだらインライン登録から消える
  await expect(page.getByTestId('llmkey-input-gemini')).toHaveCount(0)

  // 選択中のプロバイダは登録済みでも表示され、その場で差し替え・削除できる
  await provider.selectOption('gemini')
  await expect(page.getByTestId('llm-key-setup')).toContainText('登録済み …tkey')
  await expect(page.getByTestId('llmkey-input-gemini')).toBeVisible()
  await expect(page.getByTestId('llmkey-delete-gemini')).toBeVisible()
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
