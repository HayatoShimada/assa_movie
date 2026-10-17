/**
 * 画面の操作とジョブの対応(どのボタンの進捗か)。
 *
 * 進捗を出すジョブIDを各タブのstateだけで持っていると、タブ切替(アンマウント)や
 * 再読み込みで失い、処理中なのに進捗が消えてボタンがまた押せる状態に戻る。
 * ジョブIDは枠(key)ごとにストアへ預け、無ければ実行中のジョブ
 * (GET /api/jobs/active)から、その枠に当たるものを拾い直す。
 *
 * 種別だけでは見分けられないものがある:
 * - resolve: レビュータブの「指示語を解決」とクリップの「自己完結化」(clip_id で分かれる)
 * - export: 書き出しタブの範囲指定とクリップの書き出し(clip_id で分かれる)
 */
import type { Job } from '../api/client'
import type { JobProgress } from '../hooks/useJobProgress'

type JobLike = Pick<Job, 'type' | 'media_id' | 'params'>

export interface JobSlot {
  /** ストアに預けるときの名前。メディア・クリップごとに分かれる */
  key: string
  matches: (job: JobLike) => boolean
}

function clipIdOf(job: JobLike): number | null {
  const id = job.params?.clip_id
  return typeof id === 'number' ? id : null
}

function slot(mediaId: number | null, name: string, matches: (job: JobLike) => boolean): JobSlot {
  return {
    key: `${mediaId ?? '-'}:${name}`,
    matches: (job) => job.media_id === mediaId && matches(job),
  }
}

export const jobSlots = {
  /** ホームの文字起こし */
  transcribe: (mediaId: number) => slot(mediaId, 'transcribe', (j) => j.type === 'transcribe'),
  /** 質問タブの「固有名詞をスキャン」 */
  scanTerms: (mediaId: number) => slot(mediaId, 'extract_terms', (j) => j.type === 'extract_terms'),
  /** レビュータブの「指示語を解決」「未解決のみ再実行」 */
  resolve: (mediaId: number) =>
    slot(mediaId, 'resolve', (j) => j.type === 'resolve' && clipIdOf(j) === null),
  /** クリップタブの「切り抜き候補を探す」 */
  suggestClips: (mediaId: number) => slot(mediaId, 'attention', (j) => j.type === 'attention'),
  /** クリップの「指示語を自己完結化」 */
  clipResolve: (mediaId: number, clipId: number) =>
    slot(mediaId, `clip:${clipId}:resolve`, (j) => j.type === 'resolve' && clipIdOf(j) === clipId),
  /** クリップの「タイトル・メタ生成」 */
  clipMeta: (mediaId: number, clipId: number) =>
    slot(mediaId, `clip:${clipId}:meta`, (j) => j.type === 'clip_meta' && clipIdOf(j) === clipId),
  /** クリップの「書き出し」 */
  clipExport: (mediaId: number, clipId: number) =>
    slot(mediaId, `clip:${clipId}:export`, (j) => j.type === 'export' && clipIdOf(j) === clipId),
  /** 書き出しタブの範囲指定の書き出し */
  exportRange: (mediaId: number) =>
    slot(mediaId, 'export', (j) => j.type === 'export' && clipIdOf(j) === null),
  /** 種別だけで決まるジョブ(書き出しタブのフィラー検出・字幕ジャッジ) */
  mediaJob: (mediaId: number, type: string) => slot(mediaId, type, (j) => j.type === type),
  /** 設定タブ・初回セットアップのモデル取得(メディアに紐づかない) */
  setup: (item: string) => slot(null, `setup:${item}`, (j) => j.type === `setup_${item}`),
}

/**
 * 表示するジョブIDを決める。
 *
 * 覚えているIDがあればそれ(終わったジョブでも完了・失敗を見せられる)。
 * ただしそれより新しい実行中のジョブがあればそちら(別の窓から始めた等)。
 * 覚えていなければ(再読み込み後)、実行中のジョブから拾う。
 */
export function pickJobId(
  stored: number | undefined,
  active: readonly (JobLike & { id: number })[],
  slot: JobSlot,
): number | null {
  const running = active.filter((j) => slot.matches(j)).map((j) => j.id)
  const newest = running.length ? Math.max(...running) : null
  if (newest !== null && (stored === undefined || newest > stored)) return newest
  return stored ?? null
}

/**
 * 実行中で、もう一度押させてはいけないか。
 *
 * 取り直した直後はSSEの最初の通知がまだ来ていない(状態は idle)。
 * その間も、実行中の一覧に載っていれば押させない。
 */
export function isJobBusy(
  status: JobProgress['status'],
  jobId: number | null,
  active: readonly { id: number }[],
): boolean {
  if (status === 'running' || status === 'queued') return true
  if (status !== 'idle' || jobId === null) return false
  return active.some((j) => j.id === jobId)
}

/** 例外の型名(「RuntimeError: 」等)。バックエンドは「型名: 文言」で保存する */
const EXCEPTION_PREFIX = /^[A-Z][A-Za-z0-9_.]*(?:Error|Exception|Exit|Timeout): /

/** 失敗の理由(1行目)。型名は利用者には意味が無いので外す */
export function jobErrorMessage(error: string | null | undefined): string | null {
  const first = (error ?? '').split('\n')[0].trim().replace(EXCEPTION_PREFIX, '')
  return first || null
}

/**
 * 進捗バーに添える文言。始めていなければ null。
 *
 * - 順番待ちは実行中と分ける。別の動画の文字起こしの後ろで待っている間
 *   「文字起こし中... 0%」のまま19分動かず、固まったように見えた
 * - 失敗はバックエンドの文言を出す。完了以外を「〜中」と出していて、
 *   失敗しても「候補を探索中...」のまま変わらなかった
 */
export function jobStatusText(
  progress: JobProgress,
  labels: { running: string; done: string },
): string | null {
  switch (progress.status) {
    case 'idle':
      return null
    case 'queued':
      return '順番待ち(前の処理が終わると始まります)'
    case 'running':
      return `${progress.phase ?? labels.running}... ${Math.round(progress.progress * 100)}%`
    case 'completed':
      return labels.done
    case 'failed': {
      const message = jobErrorMessage(progress.error)
      return message ? `失敗: ${message}` : '失敗しました'
    }
    case 'cancelled':
      return '中止しました'
    default:
      return null
  }
}
