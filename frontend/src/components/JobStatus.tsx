/**
 * ジョブの進捗表示(順番待ち・実行中・完了・失敗・中止)。
 *
 * 各タブが「完了なら〜完了、それ以外は〜中」と書いていたため、失敗しても
 * 「〜中...」のまま変わらず、順番待ちも「〜中 0%」に見えていた。
 * 文言の決め方は lib/jobs.ts の jobStatusText に1箇所でまとめる。
 */
import type { JobProgress } from '../hooks/useJobProgress'
import { jobResultMessage, jobStatusText } from '../lib/jobs'
import { ProgressBar } from './ui'

export function JobStatus({
  progress,
  running,
  done,
  'data-testid': testId,
}: {
  progress: JobProgress
  /** 実行中の文言(「スキャン中」等。工程名が届けばそちらを出す) */
  running: string
  /** 完了の文言 */
  done: string
  'data-testid'?: string
}) {
  const text = jobStatusText(progress, { running, done })
  if (text === null) return null
  if (progress.status === 'failed') {
    return (
      <p
        role="alert"
        data-testid={testId}
        data-status="failed"
        className="break-all text-xs text-red-600 dark:text-red-400"
      >
        {text}
      </p>
    )
  }
  // 完了時の結果の説明(0件のときに何を探したか等)。無ければ従来どおりバーだけ
  const result = jobResultMessage(progress)
  if (result === null) {
    return <ProgressBar value={progress.progress} label={text} data-testid={testId} />
  }
  return (
    <div>
      <ProgressBar value={progress.progress} label={text} data-testid={testId} />
      <p
        data-testid={testId ? `${testId}-result` : undefined}
        className="mt-1 text-xs text-neutral-600 dark:text-neutral-400"
      >
        {result}
      </p>
    </div>
  )
}
