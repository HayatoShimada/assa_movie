/**
 * 書き出しタブ: 字幕ジャッジ・フィラー検出と、秒指定の書き出し(詳細)。
 *
 * 切り抜きの書き出しはクリップタブが本線。ここにも開始秒/終了秒の書き出し欄が
 * 並んでいて「どちらで書き出すのか」迷わせていたので、秒指定は「詳細」に畳む。
 * 動画の概要(ブリーフ)は文字起こしタブの先頭へ移した(components/brief)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useTrackedJob } from '../../hooks/useTrackedJob'
import { jobSlots } from '../../lib/jobs'
import { JobStatus } from '../JobStatus'
import { Button, formatTime } from '../ui'
import { ExportResult } from './ExportResult'

function JobButton({
  mediaId,
  type,
  label,
  running: runningLabel,
  params = {},
  onDone,
}: {
  mediaId: number
  type: string
  label: string
  /** 実行中の文言 */
  running: string
  params?: Record<string, unknown>
  onDone?: () => void
}) {
  // ジョブIDはタブの外に預ける(タブ切替・再読み込みで進捗を失わない)
  const { progress, busy, start } = useTrackedJob(jobSlots.mediaJob(mediaId, type), onDone)
  const run = useMutation({
    mutationFn: () => api.createJob(mediaId, type, params),
    onSuccess: (job) => start(job.id),
  })
  const running = busy || run.isPending
  return (
    <div className="space-y-1">
      <Button
        data-testid={`job-${type}`}
        variant="ghost"
        disabled={running}
        onClick={() => run.mutate()}
      >
        {label}
      </Button>
      <JobStatus
        progress={progress}
        running={runningLabel}
        done="完了"
        data-testid={`job-${type}-progress`}
      />
    </div>
  )
}

export function ExportTab({
  mediaId,
  onGoToClips,
}: {
  mediaId: number
  /** クリップタブへ切り替える(切り抜きの書き出しはそちらが本線) */
  onGoToClips?: () => void
}) {
  const queryClient = useQueryClient()
  const media = useQuery({ queryKey: ['mediaItem', mediaId], queryFn: () => api.getMedia(mediaId) })
  const duration = media.data?.duration ?? 60

  const [start, setStart] = useState(0)
  const [end, setEnd] = useState(Math.min(60, Math.round(duration)))
  const [burn, setBurn] = useState(true)
  const [resultPath, setResultPath] = useState<string | null>(null)

  // ジョブIDはタブの外に預ける(タブ切替・再読み込みで進捗を失わない)
  const exportJob = useTrackedJob(jobSlots.exportRange(mediaId), async (job) => {
    if (job.status === 'completed') {
      const full = await api.getJob(job.id)
      setResultPath((full.result as { path?: string } | null)?.path ?? null)
    }
  })
  const exportRun = useMutation({
    mutationFn: () =>
      api.createJob(mediaId, 'export', { start, end, burn_subtitles: burn }),
    onSuccess: (job) => {
      setResultPath(null)
      exportJob.start(job.id)
    },
  })
  const { progress } = exportJob
  const running = exportJob.busy || exportRun.isPending
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['segments'] })
    queryClient.invalidateQueries({ queryKey: ['edits'] })
    queryClient.invalidateQueries({ queryKey: ['questions', mediaId] })
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div
        data-testid="export-guide"
        className="space-y-1 border-b border-neutral-200 p-3 text-sm dark:border-neutral-800"
      >
        <p>
          切り抜き動画は<strong>クリップタブ</strong>で範囲を選んで書き出します。
        </p>
        {onGoToClips && (
          <Button variant="ghost" data-testid="export-go-clips" onClick={onGoToClips}>
            クリップタブを開く
          </Button>
        )}
      </div>

      <div className="space-y-2 border-b border-neutral-200 p-3 dark:border-neutral-800">
        <h3 className="text-xs font-semibold text-neutral-500">AI処理</h3>
        <div className="flex flex-wrap gap-2">
          <JobButton
            mediaId={mediaId}
            type="filler"
            label="フィラーを検出"
            running="フィラーを検出中"
            onDone={invalidateAll}
          />
          <JobButton
            mediaId={mediaId}
            type="judge_subtitles"
            label="字幕採用をジャッジ"
            running="字幕採用をジャッジ中"
            onDone={invalidateAll}
          />
        </div>
      </div>

      {/* この欄から書き出したことがあれば(タブを切り替えて戻っても)開いておく。
          進捗と保存先が畳まれて見えなくならないように */}
      <details
        data-testid="export-advanced"
        className="space-y-2 p-3"
        open={exportJob.jobId !== null ? true : undefined}
      >
        <summary className="cursor-pointer text-xs font-semibold text-neutral-500">
          詳細: 開始秒と終了秒を指定して書き出す
        </summary>
        <div className="flex items-center gap-2 text-sm">
          <label>
            開始(秒)
            <input
              data-testid="export-start"
              type="number"
              min={0}
              className="ml-1 w-20 rounded border border-neutral-300 px-1 py-0.5 dark:border-neutral-700 dark:bg-neutral-900"
              value={start}
              onChange={(e) => setStart(Number(e.target.value))}
            />
          </label>
          <label>
            終了(秒)
            <input
              data-testid="export-end"
              type="number"
              className="ml-1 w-20 rounded border border-neutral-300 px-1 py-0.5 dark:border-neutral-700 dark:bg-neutral-900"
              value={end}
              onChange={(e) => setEnd(Number(e.target.value))}
            />
          </label>
          <span className="text-xs text-neutral-500">
            (全体 {formatTime(duration)})
          </span>
        </div>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={burn} onChange={(e) => setBurn(e.target.checked)} />
          字幕を焼き込む(指示語注釈・フィラー除去・採用ジャッジを反映)
        </label>
        <Button
          data-testid="export-run"
          disabled={running || end <= start}
          onClick={() => exportRun.mutate()}
        >
          書き出し
        </Button>
        <JobStatus
          progress={progress}
          running="書き出し中"
          done="書き出し完了"
          data-testid="export-status"
        />
        {exportJob.jobId !== null && resultPath && (
          <ExportResult jobId={exportJob.jobId} path={resultPath} testId="export-result" />
        )}
      </details>
    </div>
  )
}
