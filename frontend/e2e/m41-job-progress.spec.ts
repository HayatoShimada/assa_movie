/**
 * M41: 処理中にタブを切り替えても(再読み込みしても)進捗が消えない。
 *
 * 利用者の報告: 質問タブで「固有名詞をスキャン」の途中に別のタブへ移って戻ると、
 * 進捗が消えてボタンがまた押せる状態になっていた。ジョブIDを各タブの
 * コンポーネントのstateで持っていたため、タブ切替のアンマウントで失われていた。
 * レビュー・クリップ・書き出し・ホームの文字起こしも同じ作りだった。
 *
 * FakeLLMは一瞬で終わるので、関所(holdJobs)でジョブを実行中のまま止めて観測する。
 *
 * あわせて、ジョブの状態の出し分けも確かめる(初心者目線の評価で見つかったもの):
 * - 失敗しても「候補を探索中...」のまま2分以上変わらなかった → 失敗と理由を出す
 * - 別の動画の文字起こしの後ろで待つ間「文字起こし中... 0%」のまま19分動かなかった
 *   → 順番待ちと出す
 */
import { expect, test, type Page } from '@playwright/test'
import { API, failJobs, holdJobs, releaseJobs, reset, seed, seedTranscribed } from './helpers'

/** 別のタブへ移ってから戻る */
async function leaveAndReturn(page: Page, tab: string) {
  await page.getByTestId('tab-transcript').click()
  await expect(page.getByTestId(`tab-${tab}`)).not.toHaveAttribute('aria-current', 'page')
  await page.getByTestId(`tab-${tab}`).click()
}

test('質問: スキャン中にタブを切り替えて戻っても進捗が見え、二重に押せない', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-questions').click()
  await page.getByTestId('run-scan').click()
  await expect(page.getByText('スキャン中...')).toBeVisible()

  await leaveAndReturn(page, 'questions')
  await expect(page.getByText('スキャン中...')).toBeVisible()
  await expect(page.getByTestId('run-scan')).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByText('スキャン完了')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('反動体')).toBeVisible()
  await expect(page.getByTestId('run-scan')).toBeEnabled()
})

test('質問: スキャン中に再読み込みしても進捗が見え、二重に押せない', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-questions').click()
  await page.getByTestId('run-scan').click()
  await expect(page.getByText('スキャン中...')).toBeVisible()

  // 実行中のジョブはバックエンドが知っている。そこから取り直す
  await page.reload()
  await page.getByTestId('tab-questions').click()
  await expect(page.getByText('スキャン中...')).toBeVisible()
  await expect(page.getByTestId('run-scan')).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByText('スキャン完了')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('反動体')).toBeVisible()
})

test('質問: 別のタブにいる間に終わっても、戻れば完了が分かる', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-questions').click()
  await page.getByTestId('run-scan').click()
  await expect(page.getByText('スキャン中...')).toBeVisible()

  await page.getByTestId('tab-transcript').click()
  await releaseJobs(request)
  await expect
    .poll(
      async () =>
        (await (await request.get(`${API}/api/media/${mediaId}/questions`)).json()).length,
      {
        timeout: 15000,
      },
    )
    .toBe(1)

  await page.getByTestId('tab-questions').click()
  await expect(page.getByText('スキャン完了')).toBeVisible()
  await expect(page.getByText('反動体')).toBeVisible()
})

test('レビュー: 指示語の解決中にタブを切り替えて戻っても進捗が見える', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()
  await expect(page.getByText('解決中...')).toBeVisible()

  await leaveAndReturn(page, 'review')
  await expect(page.getByText('解決中...')).toBeVisible()
  await expect(page.getByTestId('run-resolve')).toBeDisabled()
  await expect(page.getByRole('button', { name: '未解決のみ再実行' })).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByText('解決完了')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('[data-testid^="review-"]')).toHaveCount(1)
})

test('クリップ: 候補の探索中にタブを切り替えて戻っても進捗が見える', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByTestId('run-suggest').click()
  await expect(page.getByText('候補を探索中...')).toBeVisible()

  await leaveAndReturn(page, 'clips')
  await expect(page.getByText('候補を探索中...')).toBeVisible()
  await expect(page.getByTestId('run-suggest')).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByText('候補生成完了')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('ハッカソンの話')).toBeVisible()
})

test('クリップ: 自己完結化の途中にタブを切り替えて戻っても進捗が見える', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await request.post(`${API}/api/media/${mediaId}/clips`, {
    data: { start: 0, end: 8, title: '自己完結' },
  })
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('自己完結').click()
  await page.getByRole('button', { name: '指示語を自己完結化' }).click()
  await expect(page.getByText('解決中...')).toBeVisible()

  await leaveAndReturn(page, 'clips')
  await page.getByText('自己完結').click()
  await expect(page.getByText('解決中...')).toBeVisible()
  await expect(page.getByRole('button', { name: '指示語を自己完結化' })).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByText(/自己完結化完了/)).toBeVisible({ timeout: 15000 })
})

test('書き出し: フィラー検出中にタブを切り替えて戻っても進捗が見える', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-export').click()
  const button = page.getByRole('button', { name: 'フィラーを検出' })
  await button.click()
  await expect(page.getByTestId('job-filler-progress')).toBeVisible()
  await expect(button).toBeDisabled()

  await leaveAndReturn(page, 'export')
  await expect(page.getByTestId('job-filler-progress')).toBeVisible()
  await expect(button).toBeDisabled()

  await releaseJobs(request)
  await expect(button).toBeEnabled({ timeout: 15000 })
})

test('ホーム: 文字起こし中に再読み込みしても状態と中止ボタンが残る', async ({ page, request }) => {
  const { media_id } = await seed(request)
  await holdJobs(request)
  await page.goto('/')
  const row = page.getByTestId(`media-${media_id}`)
  await row.getByTestId(`media-transcribe-${media_id}`).click()
  await expect(row.getByTestId(`media-state-${media_id}`)).toHaveText('文字起こし中')

  await page.reload()
  await expect(row.getByTestId(`media-state-${media_id}`)).toHaveText('文字起こし中')
  await expect(row.getByTestId(`media-cancel-${media_id}`)).toBeVisible()

  await releaseJobs(request)
  await expect(row.getByTestId(`media-state-${media_id}`)).toHaveText('文字起こし済み', {
    timeout: 15000,
  })
})

test('設定: モデル取得中にタブを切り替えて戻っても進捗が見え、二重に押せない', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-settings').click()
  const fetch = page.getByTestId('setup-fetch-diarization')
  await fetch.click()
  await expect(fetch).toContainText('取得中')

  await leaveAndReturn(page, 'settings')
  await expect(fetch).toContainText('取得中')
  await expect(fetch).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByTestId('setup-state-diarization')).toContainText('準備できています', {
    timeout: 15000,
  })
})

// ---- 失敗の表示 ----
const FAILURES = [
  { tab: 'questions', button: 'run-scan', status: 'scan-status', type: 'extract_terms' },
  { tab: 'review', button: 'run-resolve', status: 'resolve-status', type: 'resolve' },
  { tab: 'clips', button: 'run-suggest', status: 'suggest-status', type: 'attention' },
  { tab: 'export', button: 'job-filler', status: 'job-filler-progress', type: 'filler' },
]

for (const f of FAILURES) {
  test(`失敗: ${f.tab}タブの${f.type}が失敗したら、理由を出して進捗を止める`, async ({
    page,
    request,
  }) => {
    const mediaId = await seedTranscribed(request)
    // バックエンドは「RuntimeError: 文言」で保存する。型名は画面に出さない
    await failJobs(request, f.type, 'Ollama呼び出しに3回失敗: 404')
    await page.goto(`/#/media/${mediaId}`)
    await page.getByTestId(`tab-${f.tab}`).click()
    await page.getByTestId(f.button).click()

    const status = page.getByTestId(f.status)
    await expect(status).toHaveText('失敗: Ollama呼び出しに3回失敗: 404', { timeout: 15000 })
    await expect(status).not.toContainText('中...')
    // 失敗したらやり直せる
    await expect(page.getByTestId(f.button)).toBeEnabled()

    // タブを切り替えて戻っても失敗が分かる
    await leaveAndReturn(page, f.tab)
    await expect(page.getByTestId(f.status)).toHaveText('失敗: Ollama呼び出しに3回失敗: 404')
  })
}

// ---- 順番待ちの表示 ----
test('順番待ち: 前のジョブの後ろで待つ間は「順番待ち」と出し、再読み込みしても押せない', async ({
  page,
  request,
}) => {
  const mediaId = await seedTranscribed(request)
  await holdJobs(request)
  await page.goto(`/#/media/${mediaId}`)
  // 先に1本走らせておく(ワーカーは1本なので、後のジョブは待たされる)
  await page.getByTestId('tab-questions').click()
  await page.getByTestId('run-scan').click()
  await expect(page.getByTestId('scan-status')).toContainText('スキャン中')

  await page.getByTestId('tab-review').click()
  await page.getByTestId('run-resolve').click()
  await expect(page.getByTestId('resolve-status')).toContainText('順番待ち')
  await expect(page.getByTestId('resolve-status')).not.toContainText('解決中')
  await expect(page.getByTestId('run-resolve')).toBeDisabled()

  await page.reload()
  await page.getByTestId('tab-review').click()
  await expect(page.getByTestId('resolve-status')).toContainText('順番待ち')
  await expect(page.getByTestId('run-resolve')).toBeDisabled()

  await releaseJobs(request)
  await expect(page.getByTestId('resolve-status')).toHaveText('解決完了', { timeout: 15000 })
})

test('順番待ち(ホーム): 別の動画の文字起こしを待つ間は「順番待ち」と出し、再読み込みしても残る', async ({
  page,
  request,
}) => {
  await reset(request)
  const first = (await (await request.post(`${API}/api/e2e/seed`)).json()).media_id
  const second = (await (await request.post(`${API}/api/e2e/seed`)).json()).media_id
  await holdJobs(request)
  await page.goto('/')

  await page.getByTestId(`media-transcribe-${first}`).click()
  await expect(page.getByTestId(`media-state-${first}`)).toHaveText('文字起こし中')
  await page.getByTestId(`media-transcribe-${second}`).click()
  await expect(page.getByTestId(`media-state-${second}`)).toHaveText('順番待ち')
  await expect(page.getByTestId(`media-progress-${second}`)).toContainText('順番待ち')
  await expect(page.getByTestId(`media-progress-${second}`)).not.toContainText('文字起こし中')

  await page.reload()
  await expect(page.getByTestId(`media-state-${first}`)).toHaveText('文字起こし中')
  await expect(page.getByTestId(`media-state-${second}`)).toHaveText('順番待ち')
  await expect(page.getByTestId(`media-cancel-${second}`)).toBeVisible()

  await releaseJobs(request)
  for (const id of [first, second]) {
    await expect(page.getByTestId(`media-state-${id}`)).toHaveText('文字起こし済み', {
      timeout: 20000,
    })
  }
})
