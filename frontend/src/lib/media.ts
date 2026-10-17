/**
 * 動画・クリップの見せ方(表示名と状態ラベル)。
 *
 * DBの状態名(registered / transcribed / suggested …)を画面にそのまま出すと、
 * 利用者には意味が通じない。表示の言葉はここに集めて、ホームと編集画面で揃える。
 */
import type { JobProgress } from '../hooks/useJobProgress'

/** アップロード時に保存名の前へ付く衝突よけ(uuid4().hex + "_")。backend/api/projects.py */
const UPLOAD_PREFIX = /^[0-9a-f]{32}_(?=.)/

/** パスから利用者に見せるファイル名を取り出す(Windowsの「\」区切りにも対応) */
export function mediaDisplayName(path: string): string {
  const base = path.split(/[\\/]/).pop() ?? path
  return base.replace(UPLOAD_PREFIX, '')
}

export type StateTone = 'neutral' | 'busy' | 'done' | 'error'

export interface MediaState {
  label: string
  tone: StateTone
}

const MEDIA_STATUS: Record<string, MediaState> = {
  registered: { label: '文字起こし前', tone: 'neutral' },
  transcribed: { label: '文字起こし済み', tone: 'done' },
}

/**
 * 動画の状態。画面から始めたジョブの状態はDBより新しいので、そちらを優先する。
 * 中止・失敗のときは、前回の結果が残っていればそれを見せる(再文字起こしの中止など)。
 */
export function mediaState(status: string, job: JobProgress['status']): MediaState {
  const saved = MEDIA_STATUS[status] ?? { label: status, tone: 'neutral' }
  switch (job) {
    case 'queued':
      return { label: '順番待ち', tone: 'busy' }
    case 'running':
      return { label: '文字起こし中', tone: 'busy' }
    case 'failed':
      return { label: '失敗', tone: 'error' }
    case 'cancelled':
      return status === 'transcribed' ? saved : { label: '中止', tone: 'neutral' }
    case 'completed':
      return MEDIA_STATUS.transcribed
    default:
      return saved
  }
}

const CLIP_STATUS: Record<string, string> = {
  suggested: 'AI候補',
  draft: '自分で作成',
  exporting: '書き出し中',
  exported: '書き出し済み',
}

export function clipStatusLabel(status: string): string {
  return CLIP_STATUS[status] ?? status
}
