/**
 * AIの設定と失敗の分かりやすさ(v2.0.0 初心者評価の指摘)。
 *
 * - 既定の Ollama モデル(qwen3:32b)が入っていない機体で、AI機能が全部
 *   「Ollama呼び出しに3回失敗: 404」で失敗するまで気付けなかった
 * - AIに指示の失敗が「API 500: Internal Server Error」とだけ出た
 * - 指示語の解決・固有名詞のスキャンが0件のとき「完了」とだけ出た
 *
 * Ollama の状態とAIの応答は E2E サーバーの差し替え(/api/e2e/ollama・/api/e2e/llm)で作る。
 */
import { expect, test, type APIRequestContext } from '@playwright/test'
import { API, reset, seedTranscribed } from './helpers'

// 評価機(24GB)に実際に入っていたもの。既定の qwen3:32b は入っていない
const EVAL_MODELS = [
  { name: 'gemma4:26b', vram_mb: 20402 },
  { name: 'qwen2.5:32b', vram_mb: 21771 },
]

async function setOllama(
  request: APIRequestContext,
  state: { reachable: boolean; models: { name: string; vram_mb: number }[] },
) {
  await request.post(`${API}/api/e2e/ollama`, { data: state })
}

async function setLlm(request: APIRequestContext, mode: 'normal' | 'empty' | 'missing_model') {
  await request.post(`${API}/api/e2e/llm?mode=${mode}`)
}

async function asGpuMachine(request: APIRequestContext) {
  await request.post(`${API}/api/e2e/profile?gpu=radeon`)
}

test('AIモデルが未インストールならホームで知らせ、おすすめに切り替えられる', async ({
  page,
  request,
}) => {
  await reset(request)
  await asGpuMachine(request)
  await setOllama(request, { reachable: true, models: EVAL_MODELS })
  await page.goto('/')

  const banner = page.getByTestId('llm-status-banner')
  await expect(banner).toBeVisible()
  await expect(page.getByTestId('llm-status-message')).toContainText(
    'AIモデル「qwen3:32b」がこのPCにインストールされていません',
  )
  // 直し方: おすすめを適用 / 別のモデルを選ぶ / ollama pull
  await expect(page.getByTestId('llm-pull-command')).toHaveText('ollama pull qwen3:32b')
  await expect(page.getByTestId('llm-pick-model').locator('option')).toHaveCount(3)
  const apply = page.getByTestId('llm-apply-recommended')
  await expect(apply).toHaveText('おすすめの「qwen2.5:32b」に切り替える')
  await apply.click()

  await expect(banner).toBeHidden()
  const values = (await (await request.get(`${API}/api/settings`)).json()).values
  expect(values.ollama_model).toBe('qwen2.5:32b')
})

test('Ollamaが起動していなければ編集画面で知らせ、起動後に確かめ直せる', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await setOllama(request, { reachable: false, models: [] })
  await page.goto(`/#/media/${mediaId}`)

  await expect(page.getByTestId('llm-status-message')).toContainText('Ollama が起動していません')

  // Ollamaを起動した(既定のモデルも入っている)
  const settings = await (await request.get(`${API}/api/settings`)).json()
  await setOllama(request, {
    reachable: true,
    models: [{ name: settings.values.ollama_model, vram_mb: 21000 }],
  })
  await page.getByTestId('llm-recheck').click()
  await expect(page.getByTestId('llm-status-banner')).toBeHidden()
})

test('AIに指示が失敗したら、生のエラーではなく直し方を出す', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await setLlm(request, 'missing_model')
  await page.goto(`/#/media/${mediaId}`)

  await page.getByTestId('segment-2').click()
  await page.getByTestId('assist-input').fill('反動体は半導体の誤認識です')
  await page.getByRole('button', { name: '送信' }).click()

  const error = page.getByTestId('assist-error')
  await expect(error).toContainText('インストールされていません')
  await expect(error).toContainText('ollama pull')
  await expect(error).not.toContainText('API 5')
  await expect(error).not.toContainText('{')
})

test('AIのジョブが失敗したら、直し方の文言で出す', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await setLlm(request, 'missing_model')
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()

  const status = page.getByTestId('resolve-status')
  await expect(status).toContainText('インストールされていません', { timeout: 15000 })
  await expect(status).not.toContainText('LLMError')
  await expect(status).not.toContainText('3回失敗')
})

test('指示語が0件なら、何を探したかを説明する', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await setLlm(request, 'empty')
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()

  const result = page.getByTestId('resolve-status-result')
  await expect(result).toContainText('見つかりませんでした', { timeout: 15000 })
  await expect(result).toContainText('これ・それ・あれ')
})

test('固有名詞のスキャンが0件なら、そう説明し「スキャンで探せます」とは言わない', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await setLlm(request, 'empty')
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-questions').click()
  await expect(page.getByTestId('questions-empty')).toContainText('「固有名詞をスキャン」で')

  await page.getByTestId('run-scan').click()
  await expect(page.getByTestId('scan-status-result')).toContainText('見つかりませんでした', {
    timeout: 15000,
  })
  await expect(page.getByTestId('questions-empty')).not.toContainText('「固有名詞をスキャン」で')
})

test('用語(指示語・相槌・固有名詞)に説明が付いている', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto(`/#/media/${mediaId}`)

  await page.getByTestId('help-相槌').hover()
  await expect(page.getByRole('tooltip', { name: /聞き手の短い返事/ })).toBeVisible()

  await page.getByTestId('tab-review').click()
  await page.getByTestId('help-指示語').focus()
  await expect(page.getByRole('tooltip', { name: /前に出た内容を指す言葉/ })).toBeVisible()

  await page.getByTestId('tab-questions').click()
  await page.getByTestId('help-固有名詞').hover()
  await expect(page.getByRole('tooltip', { name: /人名・会社名/ })).toBeVisible()
})

test('設定は「基本」と「詳しい設定」に分かれ、各項目に説明がある', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await asGpuMachine(request)
  await setOllama(request, { reachable: true, models: EVAL_MODELS })
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()

  const basic = page.getByTestId('setting-basic')
  await expect(basic).toContainText('字幕サイズ')
  await expect(basic).toContainText('使うAI')
  // 専門用語の項目は畳んである
  await expect(page.getByTestId('setting-asr-model')).toBeHidden()
  await expect(page.getByText('指示語置換の適用モード')).toBeHidden()
  await page.getByTestId('setting-advanced').locator('summary').click()
  await expect(page.getByTestId('setting-asr-model')).toBeVisible()
  await expect(page.getByText(/AIの提案をそのまま字幕に反映するか/)).toBeVisible()

  // 24GB機で20GB前後のモデルは収まる扱い。VRAM目安の前提も書いてある
  const model = page.getByTestId('setting-ollama-model')
  await expect(model.locator('option', { hasText: 'qwen2.5:32b' })).toContainText('おすすめ')
  await expect(model.locator('option', { hasText: 'gemma4:26b' })).not.toContainText('遅くなります')
  await expect(page.getByTestId('setting-ollama-vram-note')).toContainText('同時には動かない')
  // 選んでいる既定モデルは入っていないので、その場で直し方を出す
  await expect(page.getByTestId('setting-ollama-missing')).toContainText('ollama pull qwen3:32b')
})

test('初回セットアップでインストール済みのモデルから選べ、おすすめが既定になる', async ({
  page,
  request,
}) => {
  await reset(request)
  await asGpuMachine(request)
  await setOllama(request, { reachable: true, models: EVAL_MODELS })
  await request.patch(`${API}/api/settings`, { data: { setup_completed: false } })
  await page.goto('/')

  await page.getByTestId('wizard-next').click() // 環境 → AI
  await page.getByTestId('wizard-llm-provider').selectOption('ollama')

  const model = page.getByTestId('wizard-ollama-model')
  await expect(model).toHaveValue('qwen2.5:32b')
  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values.ollama_model)
    .toBe('qwen2.5:32b')

  // 別のモデルも選べる
  await model.selectOption('gemma4:26b')
  await expect
    .poll(async () => (await (await request.get(`${API}/api/settings`)).json()).values.ollama_model)
    .toBe('gemma4:26b')
})
