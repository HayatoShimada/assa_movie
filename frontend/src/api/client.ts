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
  cancelJob: (jobId: number) => post<Job>(`/api/jobs/${jobId}/cancel`),

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
  /** 実行環境の再検出(GPU増設・ドライバ導入後の追従手段) */
  redetectEnvironment: () => post<EnvironmentResponse>('/api/environment/redetect'),
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
  /** trueならこの機体では取得しないと文字起こしができない */
  required: boolean
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

/** 初回起動で確定した実行環境(backend/core/hwprofile.py)。再検出でのみ変わる */
export interface HwProfile {
  os: 'linux' | 'windows' | 'mac'
  gpu: 'nvidia' | 'radeon' | 'apple' | 'cpu'
  gpu_name: string
  vram_total_mb: number
  whispercpp_ok: boolean
  detected_at: string
}

/** プロファイルから決まる文字起こしの構成(コード内の静的対応表が決める) */
export interface ResolvedEngine {
  engine: 'whispercpp' | 'faster_whisper'
  device: 'vulkan' | 'metal' | 'cpu'
  compute_type: string
  label: string
  /** trueならwhisper.cppモデル(3.1GB)の取得が文字起こしに必須 */
  needs_whispercpp_model: boolean
}

export interface EnvironmentResponse {
  profile: HwProfile
  resolved: ResolvedEngine
  /** 検出時に見つかった問題(GPUがあるのにwhisper.cppを起動できない等) */
  warnings: string[]
  gpu: { name?: string; vram_total_mb?: number }
  ffmpeg: boolean
  encoder: string | null
  ollama: { reachable: boolean; models: { name: string; vram_mb: number }[] }
  recommendations: { asr_model: string; ollama_model: string | null }
  ollama_options: { name: string; vram_mb: number; fits: boolean }[]
}

/** GPUクラスの表示名 */
export const GPU_LABELS: Record<HwProfile['gpu'], string> = {
  nvidia: 'NVIDIA',
  radeon: 'AMD Radeon',
  apple: 'Apple Silicon',
  cpu: 'GPUなし',
}

export const OS_LABELS: Record<HwProfile['os'], string> = {
  linux: 'Linux',
  windows: 'Windows',
  mac: 'macOS',
}

export interface AssistResponse {
  reply: string
  edits: Edit[]
  instruction_suggestion: string | null
}

export interface SettingsResponse {
  values: Record<string, unknown>
  /** falseならモデル未取得で話者分離を使えない */
  diarization_ready: boolean
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

/**
 * ジョブがこれ以上進まない状態(backend/jobs/queue.py の TERMINAL_STATUSES と対応)。
 *
 * 各所で文字列を直に書くと取りこぼす。実際 SetupPanel は存在しない状態名を
 * 待っていて、ダウンロードが終わってもボタンが「取得中…」のまま固まっていた。
 */
export const JOB_TERMINAL_STATUSES = ['completed', 'failed', 'cancelled'] as const

export function isJobDone(status: string): boolean {
  return (JOB_TERMINAL_STATUSES as readonly string[]).includes(status)
}

/** ジョブ進捗をSSEで購読する。戻り値を呼ぶと購読を止める。 */
export function subscribeJob(jobId: number, onProgress: (job: Job) => void): () => void {
  const source = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`)
  source.addEventListener('progress', (e) => {
    const job = JSON.parse((e as MessageEvent).data) as Job & { job_id: number }
    onProgress(job)
    if (isJobDone(job.status)) source.close()
  })
  source.onerror = () => source.close()
  return () => source.close()
}
