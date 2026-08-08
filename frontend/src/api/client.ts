/**
 * 型付きAPIクライアント。
 *
 * 型は schema.d.ts (バックエンドのOpenAPIから自動生成) を参照するので、
 * APIを変えたら `npm run gen:api` を実行すれば型エラーで追従漏れが分かる。
 */
import type { components } from './schema'

export type Project = components['schemas']['Project']
export type Orientation = Project['output_orientation']
export type Media = components['schemas']['Media']
export type Job = components['schemas']['Job']
export type Segment = components['schemas']['Segment']
export type Edit = components['schemas']['Edit']
export type Question = components['schemas']['Question']

declare global {
  interface Window {
    /** Tauriシェルが起動時に注入する、Pythonバックエンドの実URL */
    __KS_API_BASE__?: string
  }
}

/**
 * APIのベースURLを決める。
 *
 * ブラウザ開発時は同一オリジン(Viteプロキシ経由)なので空文字。
 * Tauriのwebviewは `tauri://localhost` で動くため同一オリジンではPythonに届かず、
 * シェル側が実際に確保したポートを `window.__KS_API_BASE__` に注入する
 * (ポートは起動のたびに変わるので、ここに固定値は書けない)。
 */
export function resolveApiBase(w: Pick<Window, '__KS_API_BASE__'> = window): string {
  return w.__KS_API_BASE__ ?? ''
}

export const API_BASE = resolveApiBase()

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
  const isFormData = init?.body instanceof FormData
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: isFormData ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
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
  createProject: (body: {
    name: string
    input_orientation?: Orientation
    output_orientation?: Orientation
    settings?: Record<string, unknown>
  }) => post<Project>('/api/projects', body),
  getProject: (projectId: number) => request<Project>(`/api/projects/${projectId}`),
  updateProject: (
    projectId: number,
    patch: {
      name?: string
      input_orientation?: Orientation
      output_orientation?: Orientation
      settings?: Record<string, unknown>
    },
  ) => request<Project>(`/api/projects/${projectId}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteProject: (projectId: number) =>
    request<{ deleted: number }>(`/api/projects/${projectId}`, { method: 'DELETE' }),
  listMedia: (projectId: number) => request<Media[]>(`/api/projects/${projectId}/media`),
  getMedia: (mediaId: number) => request<Media>(`/api/media/${mediaId}`),
  addMedia: (projectId: number, path: string) =>
    post<Media>(`/api/projects/${projectId}/media`, { path }),
  uploadMedia: (projectId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Media>(`/api/projects/${projectId}/media/upload`, { method: 'POST', body: form })
  },

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
  getFonts: () => request<{ fonts: string[] }>('/api/fonts'),
  getSetupStatus: () => request<Record<string, SetupItem>>('/api/setup'),
  createSetupJob: (item: string) => post<Job>(`/api/setup/${item}`),
  getApiKeys: () => request<Record<string, ApiKeyStatus>>('/api/keys'),
  registerApiKey: (provider: string, key: string) =>
    request<Record<string, ApiKeyStatus>>(`/api/keys/${provider}`, {
      method: 'PUT',
      body: JSON.stringify({ key }),
    }),
  deleteApiKey: (provider: string) =>
    request<Record<string, ApiKeyStatus>>(`/api/keys/${provider}`, { method: 'DELETE' }),
  getLicense: () => request<LicenseStatus>('/api/license'),
  registerLicense: (key: string) =>
    request<LicenseStatus>('/api/license', { method: 'POST', body: JSON.stringify({ key }) }),
  getEnvironment: () => request<EnvironmentResponse>('/api/environment'),
}

/**
 * マシン構成のクエリ設定。
 *
 * /api/environment はOllamaへのプローブ(最大2秒)とGPU問い合わせ、
 * /api/fonts は fc-list の起動を伴う。セッション中に変わらない情報なので、
 * パネルを開くたびに再スキャンしない(変わる操作の後は明示的にinvalidateする)。
 */
export const machineQueryOptions = { staleTime: Infinity } as const

export interface SetupItem {
  label: string
  ready: boolean
  size_mb: number
  /** falseならアプリからは入れられない(手順を案内するだけ) */
  installable: boolean
  note: string
}

export interface ApiKeyStatus {
  label: string
  configured: boolean
  /** キーの出所。「環境変数」なら画面からは消せない */
  source: string | null
  /** 末尾4文字だけ(全文は返さない) */
  hint: string | null
}

export interface LicenseStatus {
  status: 'valid' | 'grace' | 'expired' | 'invalid' | 'missing'
  is_usable: boolean
  edition: string
  licensee: string
  issued: string | null
  expires: string | null
  seats: number
  /** 期限までの残り日数。無期限ならnull(猶予期間中は負) */
  days_left: number | null
  expiring_soon: boolean
}

export interface EnvironmentResponse {
  accel: 'cuda' | 'rocm' | 'cpu'
  gpu: { name?: string; vram_total_mb?: number; vram_free_mb?: number }
  ffmpeg: boolean
  encoder: string | null
  ollama: { reachable: boolean; models: { name: string; vram_mb: number }[] }
  vram_budget_mb: number
  effective_vram_mb: number
  recommendations: { asr_engine: string; asr_model: string; ollama_model: string | null }
  asr_options: { model: string; engine: string; vram_mb: number; fits: boolean }[]
  ollama_options: { name: string; vram_mb: number; fits: boolean }[]
}

export interface AssistResponse {
  reply: string
  edits: Edit[]
  instruction_suggestion: string | null
}

export interface SettingsResponse {
  values: Record<string, unknown>
  asr_engines: { id: string; label: string }[]
  /** ready=false はモデル未取得/HFトークン未設定で選べないエンジン */
  diarization_engines: { id: string; label: string; ready: boolean }[]
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
