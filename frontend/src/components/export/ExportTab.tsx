/**
 * 書き出しタブ: 概要(ブリーフ)の編集・字幕ジャッジ・フィラー検出・クリップ書き出し。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useTrackedJob } from '../../hooks/useTrackedJob'
import { jobSlots } from '../../lib/jobs'
import { JobStatus } from '../JobStatus'
import { Button, formatTime } from '../ui'

function BriefEditor({ mediaId }: { mediaId: number }) {
  const queryClient = useQueryClient()
  const brief = useQuery({
    queryKey: ['brief', mediaId],
    queryFn: () =>
      fetch(`/api/media/${mediaId}/brief`).then(
        (r) => r.json() as Promise<{ theme: string; people: string; notes: string }>,
      ),
  })
  const save = useMutation({
    mutationFn: (patch: Record<string, string>) =>
      fetch(`/api/media/${mediaId}/brief`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...brief.data, ...patch }),
      }).then((r) => r.json()),
    onSuccess: (data) => queryClient.setQueryData(['brief', mediaId], data),
  })

  if (!brief.data) return null
  const fields = [
    { key: 'theme', label: '動画全体の主題', placeholder: '例: AIと人の関わりについての対談' },
    {
      key: 'people',
      label: '登場人物の紹介',
      placeholder: '例: はやまる(古着店「箱ストア」店主)、高田さん(エッセイスト)',
    },
    {
      key: 'notes',
      label: '固有名詞・補足',
      placeholder: '例: 「箱ストア」は店名。「富山変人会」は二人が出会ったイベント',
    },
  ] as const

  return (
    <div className="space-y-2 border-b border-neutral-200 p-3 dark:border-neutral-800">
      <h3 className="text-xs font-semibold text-neutral-500">
        動画の概要(すべてのAI処理のプロンプトに注入されます)
      </h3>
      {fields.map((f) => (
        <label key={f.key} className="block text-xs">
          <span className="text-neutral-500">{f.label}</span>
          <textarea
            data-testid={`brief-${f.key}`}
            className="mt-0.5 w-full rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            rows={2}
            defaultValue={brief.data[f.key]}
            placeholder={f.placeholder}
            onBlur={(e) => {
              if (e.target.value !== brief.data[f.key]) save.mutate({ [f.key]: e.target.value })
            }}
          />
        </label>
      ))}
      {save.isSuccess && <p className="text-xs text-emerald-600">保存しました</p>}
    </div>
  )
}

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

export function ExportTab({ mediaId }: { mediaId: number }) {
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
      <BriefEditor mediaId={mediaId} />

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

      <div className="space-y-2 p-3">
        <h3 className="text-xs font-semibold text-neutral-500">クリップ書き出し</h3>
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
        {resultPath && (
          <p data-testid="export-result" className="break-all text-xs text-emerald-600">
            出力: {resultPath}
          </p>
        )}
      </div>
    </div>
  )
}
