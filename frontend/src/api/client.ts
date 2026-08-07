/**
 * 型付きAPIクライアント。
 *
 * 型は schema.d.ts (バックエンドのOpenAPIから自動生成) を参照するので、
 * APIを変えたら `npm run gen:api` を実行すれば型エラーで追従漏れが分かる。
 */
import type { components } from './schema'

export type Project = components['schemas']['Project']
export type Media = components['schemas']['Media']
export type Job = components['schemas']['Job']
export type Segment = components['schemas']['Segment']
export type Edit = components['schemas']['Edit']
export type Question = components['schemas']['Question']

// 常に同一オリジン(Viteプロキシ経由)でAPIを叩く。CORS設定は不要
export const API_BASE = ''

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  health: () => request<{ status: string }>('/api/health'),

  listProjects: () => request<Project[]>('/api/projects'),
  createProject: (name: string) => post<Project>('/api/projects', { name }),
  listMedia: (projectId: number) => request<Media[]>(`/api/projects/${projectId}/media`),
  getMedia: (mediaId: number) => request<Media>(`/api/media/${mediaId}`),
  addMedia: (projectId: number, path: string) =>
    post<Media>(`/api/projects/${projectId}/media`, { path }),

  createJob: (mediaId: number, type: string, params: Record<string, unknown> = {}) =>
    post<Job>(`/api/media/${mediaId}/jobs`, { type, params }),
  getJob: (jobId: number) => request<Job>(`/api/jobs/${jobId}`),

  listSegments: (mediaId: number, includeAizuchi = true) =>
    request<Segment[]>(
      `/api/media/${mediaId}/segments?include_aizuchi=${includeAizuchi ? 'true' : 'false'}`,
    ),
  updateSegment: (segmentId: number, patch: Partial<Pick<Segment, 'text' | 'speaker'>>) =>
    request<Segment>(`/api/segments/${segmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  listEdits: (mediaId: number, status?: string) =>
    request<Edit[]>(`/api/media/${mediaId}/edits${status ? `?status=${status}` : ''}`),
  acceptEdit: (editId: number, body: { replacement?: string; form?: string } = {}) =>
    post<Edit>(`/api/edits/${editId}/accept`, body),
  rejectEdit: (editId: number, note?: string) => post<Edit>(`/api/edits/${editId}/reject`, { note }),
  revertEdit: (editId: number) => post<Edit>(`/api/edits/${editId}/revert`),

  assistSegment: (segmentId: number, message: string) =>
    post<AssistResponse>(`/api/segments/${segmentId}/assist`, { message }),
  createInstruction: (projectId: number, text: string, mediaId?: number) =>
    post<{ id: number; text: string }>(`/api/projects/${projectId}/instructions`, {
      text,
      media_id: mediaId ?? null,
    }),

  listQuestions: (mediaId: number, status = 'open') =>
    request<Question[]>(`/api/media/${mediaId}/questions?status=${status}`),
  answerQuestion: (questionId: number, text: string) =>
    post<{ segments_changed: number }>(`/api/questions/${questionId}/answer`, { text }),
  dismissQuestion: (questionId: number) => post<Question>(`/api/questions/${questionId}/dismiss`),

  getSettings: () => request<SettingsResponse>('/api/settings'),
  updateSettings: (patch: Record<string, unknown>) =>
    request<SettingsResponse>('/api/settings', { method: 'PATCH', body: JSON.stringify(patch) }),
}

export interface AssistResponse {
  reply: string
  edits: Edit[]
  instruction_suggestion: string | null
}

export interface SettingsResponse {
  values: Record<string, unknown>
  asr_models: { id: string; label: string; rtf: number; word_timestamps: boolean; note: string }[]
  llm_providers: {
    id: string
    label: string
    local: boolean
    models: string[]
    note: string
    ready: boolean
  }[]
}

/** ジョブ進捗をSSEで購読する。戻り値を呼ぶと購読を止める。 */
export function subscribeJob(jobId: number, onProgress: (job: Job) => void): () => void {
  const source = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`)
  source.addEventListener('progress', (e) => {
    const job = JSON.parse((e as MessageEvent).data) as Job & { job_id: number }
    onProgress(job)
    if (job.status === 'completed' || job.status === 'failed') source.close()
  })
  source.onerror = () => source.close()
  return () => source.close()
}
