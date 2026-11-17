/**
 * M42: 書き出し先を見える場所にし、利用者が選べるようにする(issue #3)。
 *
 * 以前は「元動画の隣の exports/」で、ファイル選択で取り込んだ動画だとアプリの
 * データフォルダ(macOSなら ~/Library/Application Support/…。Finderでは隠れている)に
 * 書き出され、「書き出したのにどこにも無い」になっていた。
 *
 * - 既定は動画フォルダの中の KirinukiStudio/(E2Eでは一時フォルダに差し替え)
 * - 書き出す前に保存先が見え、その場で変えられる・開ける
 * - デスクトップ版はOSのフォルダ選択(Finder / エクスプローラー)。
 *   ブラウザ(開発版)はパスの入力欄
 */
import { expect, test, type Page } from '@playwright/test'
import { API, seedTranscribed } from './helpers'

async function openClip(page: Page, request: Parameters<typeof seedTranscribed>[0]) {
  const mediaId = await seedTranscribed(request)
  const clip = await (
    await request.post(`${API}/api/media/${mediaId}/clips`, {
      data: { start: 0, end: 8, title: '保存先を確かめるクリップ' },
    })
  ).json()
  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-clips').click()
  await page.getByText('保存先を確かめるクリップ').click()
  return { mediaId, clip }
}

test('書き出す前から保存先が見え、既定は動画フォルダの中の KirinukiStudio', async ({
  page,
  request,
}) => {
  await openClip(page, request)
  const path = page.getByTestId('clip-export-destination-path')
  await expect(path).toHaveText(/[\\/]KirinukiStudio$/)
  // 取り込んだ動画の置き場(アプリのデータフォルダ)の中ではない
  await expect(path).not.toHaveText(/uploads|exports/)
  // 既定のままなら「既定の場所に戻す」は出さない
  await expect(page.getByTestId('clip-export-destination-reset')).toHaveCount(0)
})

test('保存先をその場で変えると、その場所に書き出される(ブラウザ版は入力欄)', async ({
  page,
  request,
}) => {
  const { clip } = await openClip(page, request)
  const before = (await page.getByTestId('clip-export-destination-path').textContent())!
  const chosen = `${before}-選んだ場所`

  await page.getByTestId('clip-export-destination-change').click()
  await page.getByTestId('clip-export-destination-input').fill(chosen)
  await page.getByTestId('clip-export-destination-save').click()
  await expect(page.getByTestId('clip-export-destination-path')).toHaveText(chosen)
  await expect(page.getByTestId('clip-export-destination-input')).toHaveCount(0)

  await page.getByTestId('clip-export').click()
  await expect(page.getByTestId('clip-export-result')).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('clip-export-result-folder')).toHaveText(chosen)
  await expect(page.getByTestId('clip-export-result-name')).toHaveText(
    `sample_0s-8s_clip${clip.id}.mp4`,
  )

  // 既定の場所に戻せる
  await page.getByTestId('clip-export-destination-reset').click()
  await expect(page.getByTestId('clip-export-destination-path')).toHaveText(before)
})

test('デスクトップ版はOSのフォルダ選択で保存先を選ぶ', async ({ page, request }) => {
  // Tauriのwebviewにある呼び出し口を真似る。選んだことにするフォルダを返す
  await page.addInitScript(() => {
    const calls: unknown[] = []
    Object.assign(window, {
      __dialogCalls: calls,
      __TAURI_INTERNALS__: {
        invoke: async (cmd: string, args: { options: { defaultPath: string } }) => {
          calls.push({ cmd, args })
          return `${args.options.defaultPath}-Finderで選んだ`
        },
      },
    })
  })
  await openClip(page, request)
  const before = (await page.getByTestId('clip-export-destination-path').textContent())!

  await page.getByTestId('clip-export-destination-change').click()
  await expect(page.getByTestId('clip-export-destination-path')).toHaveText(
    `${before}-Finderで選んだ`,
  )
  // 入力欄は出さない。フォルダ選択として、今の保存先から開いている
  await expect(page.getByTestId('clip-export-destination-input')).toHaveCount(0)
  const calls = await page.evaluate(
    () => (window as unknown as { __dialogCalls: unknown[] }).__dialogCalls,
  )
  expect(calls).toEqual([
    {
      cmd: 'plugin:dialog|open',
      args: {
        options: {
          directory: true,
          multiple: false,
          canCreateDirectories: true,
          title: '書き出した動画の保存先を選ぶ',
          defaultPath: before,
        },
      },
    },
  ])
})

test('フォルダ選択をキャンセルしたら保存先は変わらない', async ({ page, request }) => {
  await page.addInitScript(() => {
    Object.assign(window, { __TAURI_INTERNALS__: { invoke: async () => null } })
  })
  await openClip(page, request)
  const before = (await page.getByTestId('clip-export-destination-path').textContent())!
  await page.getByTestId('clip-export-destination-change').click()
  await expect(page.getByTestId('clip-export-destination-path')).toHaveText(before)
  await expect(page.getByTestId('clip-export-destination-error')).toHaveCount(0)
})

test('使えない場所は理由と直し方を出して保存しない', async ({ page, request }) => {
  await openClip(page, request)
  const before = (await page.getByTestId('clip-export-destination-path').textContent())!
  await page.getByTestId('clip-export-destination-change').click()
  await page.getByTestId('clip-export-destination-input').fill('相対パスの場所')
  await page.getByTestId('clip-export-destination-save').click()
  await expect(page.getByTestId('clip-export-destination-error')).toContainText('先頭から')
  await expect(page.getByTestId('clip-export-destination-path')).toHaveText(before)
})

test('書き出す前でも保存先のフォルダを開ける', async ({ page, request }) => {
  await openClip(page, request)
  const path = (await page.getByTestId('clip-export-destination-path').textContent())!
  await page.getByTestId('clip-export-destination-reveal').click()
  await expect
    .poll(async () => (await request.get(`${API}/api/e2e/revealed`)).json())
    .toEqual([path])
})

test('全体の設定と、秒指定の書き出しにも同じ保存先が出る', async ({ page, request }) => {
  const mediaId = await seedTranscribed(request)
  await page.goto('/#/settings')
  const inSettings = page.getByTestId('settings-export-destination-path')
  await expect(inSettings).toHaveText(/[\\/]KirinukiStudio$/)
  const path = (await inSettings.textContent())!

  await page.goto(`/#/media/${mediaId}`)
  await page.getByTestId('tab-export').click()
  await page.getByTestId('export-advanced').locator('summary').click()
  await expect(page.getByTestId('export-destination-path')).toHaveText(path)
})
