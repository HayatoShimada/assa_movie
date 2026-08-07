/** クリップ関連の型付きAPI */
import { API_BASE, type Job } from './client'

export interface ClipCut {
  id: number
  start: number
  end: number
  source: 'silence' | 'aizuchi' | 'manual'
  active: 0 | 1
}

export interface Clip {
  id: number
  media_id: number
  start: number
  end: number
  title: string | null
  hook_text: string | null
  score: number | null
  score_reasons: string[]
  subtitle_position: 'top' | 'center' | 'bottom'
  subtitle_offset_y: number
  convert_method: 'crop' | 'blur_pad' | 'face' | null
  crop_x: number
  target_duration: number | null
  meta: { title: string; hooks: string[]; description: string; hashtags: string[] } | null
  status: string
  cuts: ClipCut[]
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export const clipsApi = {
  list: (mediaId: number) => req<Clip[]>(`/api/media/${mediaId}/clips`),
  create: (mediaId: number, start: number, end: number) =>
    req<Clip>(`/api/media/${mediaId}/clips`, {
      method: 'POST',
      body: JSON.stringify({ start, end }),
    }),
  update: (clipId: number, patch: Partial<Pick<Clip, 'start' | 'end' | 'title' | 'hook_text' | 'status' | 'subtitle_position' | 'subtitle_offset_y' | 'convert_method' | 'crop_x'>>) =>
    req<Clip>(`/api/clips/${clipId}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  remove: (clipId: number) => req<{ deleted: number }>(`/api/clips/${clipId}`, { method: 'DELETE' }),
  jetcut: (clipId: number) => req<Clip>(`/api/clips/${clipId}/jetcut`, { method: 'POST' }),
  toggleCut: (cutId: number, active: boolean) =>
    req<ClipCut>(`/api/clip_cuts/${cutId}?active=${active}`, { method: 'PATCH' }),
  resolve: (clipId: number) =>
    req<{ job_id: number }>(`/api/clips/${clipId}/resolve`, { method: 'POST' }),
  exportClip: (clipId: number) =>
    req<{ job_id: number }>(`/api/clips/${clipId}/export`, { method: 'POST' }),
  suggest: (mediaId: number, targetDuration?: number) =>
    req<Job>(`/api/media/${mediaId}/jobs`, {
      method: 'POST',
      body: JSON.stringify({
        type: 'attention',
        params: targetDuration ? { target_duration: targetDuration } : {},
      }),
    }),
  meta: (mediaId: number, clipId: number) =>
    req<Job>(`/api/media/${mediaId}/jobs`, {
      method: 'POST',
      body: JSON.stringify({ type: 'clip_meta', params: { clip_id: clipId } }),
    }),
}
