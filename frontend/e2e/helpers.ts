/** E2Eの共通ヘルパ(spec間で共有。*.spec.ts ではないのでテストとして収集されない) */
import { expect, type APIRequestContext } from '@playwright/test'

export const API = 'http://localhost:8001'

export async function reset(request: APIRequestContext) {
  await request.post(`${API}/api/e2e/reset`)
}

/** DBを空にしてプロジェクト+メディアを1件作る */
export async function seed(
  request: APIRequestContext,
  orientation: 'landscape' | 'portrait' = 'landscape',
): Promise<{ project_id: number; media_id: number }> {
  await reset(request)
  const query = orientation === 'landscape' ? '' : `?output_orientation=${orientation}`
  return (await request.post(`${API}/api/e2e/seed${query}`)).json()
}

/** シード + FakeASRで文字起こし済みにする(多くのspecの前提) */
export async function seedTranscribed(
  request: APIRequestContext,
  orientation: 'landscape' | 'portrait' = 'landscape',
): Promise<number> {
  const { media_id } = await seed(request, orientation)
  await request.post(`${API}/api/media/${media_id}/jobs`, {
    data: { type: 'transcribe_fake', params: {} },
  })
  await expect
    .poll(async () => (await (await request.get(`${API}/api/media/${media_id}`)).json()).status, {
      timeout: 15000,
    })
    .toBe('transcribed')
  return media_id
}

/**
 * ジョブを実行中のまま止めておく(backend/e2e_server.py の JOB_GATE)。
 * FakeLLMは一瞬で終わるので、止めないと「処理中」の画面を観測できない。
 * reset で必ず開くので、spec の途中で失敗しても次へ持ち越さない
 */
export async function holdJobs(request: APIRequestContext) {
  await request.post(`${API}/api/e2e/gate?open=false`)
}

export async function releaseJobs(request: APIRequestContext) {
  await request.post(`${API}/api/e2e/gate?open=true`)
}

/** この種別のジョブを、指定の文言で失敗させる(reset で元に戻る) */
export async function failJobs(request: APIRequestContext, jobType: string, message: string) {
  const query = new URLSearchParams({ job_type: jobType, message })
  await request.post(`${API}/api/e2e/fail?${query}`)
}
