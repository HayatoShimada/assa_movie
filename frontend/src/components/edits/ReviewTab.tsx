/**
 * 置換レビュータブ(Human-in-the-loopの中心)。
 * レビュー待ちの承認/修正/却下、適用済みの取り消し、追加指示付き再実行。
 * キーボード: j/k 移動, a 承認, x 却下
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, type Edit, type Segment } from '../../api/client'
import { usePlayback } from '../../stores/playback'
import { useJobProgress } from '../../hooks/useJobProgress'
import { Button, ProgressBar, formatTime } from '../ui'

function DiffText({ edit }: { edit: Edit }) {
  return (
    <p className="text-sm">
      <span className="rounded bg-red-50 px-1 text-red-700 line-through dark:bg-red-950 dark:text-red-300">
        {edit.original}
      </span>
      <span className="mx-1 text-neutral-400">→</span>
      <span className="rounded bg-emerald-50 px-1 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
        {edit.replacement}
      </span>
    </p>
  )
}

function ProposedRow({
  edit,
  segment,
  focused,
  onFocus,
}: {
  edit: Edit
  segment?: Segment
  focused: boolean
  onFocus: () => void
}) {
  const queryClient = useQueryClient()
  const seekTo = usePlayback((s) => s.seekTo)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(edit.replacement)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['edits'] })
    queryClient.invalidateQueries({ queryKey: ['segments'] })
  }
  const accept = useMutation({
    mutationFn: (replacement?: string) => api.acceptEdit(edit.id, { replacement }),
    onSuccess: invalidate,
  })
  const reject = useMutation({
    mutationFn: (note?: string) => api.rejectEdit(edit.id, note),
    onSuccess: invalidate,
  })

  return (
    <div
      data-testid={`review-${edit.id}`}
      data-focused={focused || undefined}
      onClick={onFocus}
      className={`border-b border-neutral-100 p-3 dark:border-neutral-800 ${
        focused ? 'bg-blue-50 dark:bg-blue-950' : ''
      }`}
    >
      <div className="flex items-center gap-2">
        <DiffText edit={edit} />
        {segment && (
          <button
            type="button"
            className="ml-auto shrink-0 font-mono text-xs text-blue-600 hover:underline"
            onClick={(e) => {
              e.stopPropagation()
              seekTo(segment.start)
            }}
          >
            {formatTime(segment.start)}
          </button>
        )}
      </div>
      {segment && (
        <p className="mt-1 truncate text-xs text-neutral-500" title={segment.text}>
          {segment.text}
        </p>
      )}

      {editing ? (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            accept.mutate(value)
          }}
        >
          <input
            autoFocus
            className="flex-1 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <Button type="submit">この内容で承認</Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            戻る
          </Button>
        </form>
      ) : (
        <div className="mt-2 flex gap-2">
          <Button onClick={() => accept.mutate(undefined)}>承認 (a)</Button>
          <Button variant="ghost" onClick={() => setEditing(true)}>
            修正して承認
          </Button>
          <Button variant="ghost" onClick={() => reject.mutate(undefined)}>
            却下 (x)
          </Button>
        </div>
      )}
      {(accept.isError || reject.isError) && (
        <p className="mt-1 text-xs text-red-600">
          {String((accept.error ?? reject.error)?.message)}
        </p>
      )}
    </div>
  )
}

function RerunBar({ mediaId, projectId }: { mediaId: number; projectId?: number }) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | null>(null)
  const [instruction, setInstruction] = useState('')
  const [keep, setKeep] = useState(false)
  const progress = useJobProgress(jobId, () => {
    queryClient.invalidateQueries({ queryKey: ['edits'] })
    queryClient.invalidateQueries({ queryKey: ['segments'] })
  })

  const run = useMutation({
    mutationFn: async (scope: 'all' | 'unresolved') => {
      if (instruction.trim() && keep && projectId) {
        await api.createInstruction(projectId, instruction.trim(), mediaId)
      }
      const params: Record<string, unknown> = { scope }
      // 一度きりの指示は指示テーブルに残さずジョブパラメータで渡す…はM7以降。
      // 現状は「今後も使う」= instructionsに保存、それ以外は保存せず実行のみ。
      return api.createJob(mediaId, 'resolve', params)
    },
    onSuccess: (job) => setJobId(job.id),
  })

  const running = progress.status === 'running' || progress.status === 'queued'

  return (
    <div className="space-y-2 border-b border-neutral-200 p-3 dark:border-neutral-800">
      <div className="flex gap-2">
        <Button
          data-testid="run-resolve"
          disabled={running}
          onClick={() => run.mutate('all')}
        >
          指示語を解決
        </Button>
        <Button variant="ghost" disabled={running} onClick={() => run.mutate('unresolved')}>
          未解決のみ再実行
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <input
          className="flex-1 rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="追加指示(例: 『あれ』はAIハッカソンを指す)"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
        <label className="flex items-center gap-1 text-xs text-neutral-500">
          <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
          今後も使う
        </label>
      </div>
      {jobId !== null && progress.status !== 'idle' && (
        <ProgressBar
          value={progress.progress}
          label={
            progress.status === 'failed'
              ? `失敗: ${progress.error?.split('\n')[0] ?? ''}`
              : progress.status === 'completed'
                ? '解決完了'
                : '解決中...'
          }
        />
      )}
    </div>
  )
}

export function ReviewTab({ mediaId, projectId }: { mediaId: number; projectId?: number }) {
  const queryClient = useQueryClient()
  const edits = useQuery({ queryKey: ['edits', mediaId], queryFn: () => api.listEdits(mediaId) })
  const segments = useQuery({
    queryKey: ['segments', mediaId, true],
    queryFn: () => api.listSegments(mediaId, true),
  })
  const segById = new Map((segments.data ?? []).map((s) => [s.id, s]))

  const proposed = (edits.data ?? []).filter((e) => e.status === 'proposed')
  const applied = (edits.data ?? []).filter((e) => e.status === 'applied')
  const [focusIndex, setFocusIndex] = useState(0)

  const revert = useMutation({
    mutationFn: (id: number) => api.revertEdit(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['edits'] })
      queryClient.invalidateQueries({ queryKey: ['segments'] })
    },
  })

  // キーボードレビュー: j/k 移動, a 承認, x 却下
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (proposed.length === 0) return
      const current = proposed[Math.min(focusIndex, proposed.length - 1)]
      if (e.key === 'j') setFocusIndex((i) => Math.min(i + 1, proposed.length - 1))
      if (e.key === 'k') setFocusIndex((i) => Math.max(i - 1, 0))
      if (e.key === 'a' && current) {
        api.acceptEdit(current.id, {}).then(() => {
          queryClient.invalidateQueries({ queryKey: ['edits'] })
          queryClient.invalidateQueries({ queryKey: ['segments'] })
        })
      }
      if (e.key === 'x' && current) {
        api.rejectEdit(current.id).then(() => {
          queryClient.invalidateQueries({ queryKey: ['edits'] })
        })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [proposed, focusIndex, queryClient])

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <RerunBar mediaId={mediaId} projectId={projectId} />

      <h3 className="px-3 pt-3 text-xs font-semibold text-neutral-500">
        レビュー待ち({proposed.length}件)
        {proposed.length > 0 && (
          <span className="ml-2 font-normal">j/k: 移動 a: 承認 x: 却下</span>
        )}
      </h3>
      {proposed.length === 0 && (
        <p className="px-3 py-2 text-sm text-neutral-500">レビュー待ちはありません</p>
      )}
      {proposed.map((e, i) => (
        <ProposedRow
          key={e.id}
          edit={e}
          segment={segById.get(e.segment_id)}
          focused={i === Math.min(focusIndex, proposed.length - 1)}
          onFocus={() => setFocusIndex(i)}
        />
      ))}

      <h3 className="px-3 pt-4 text-xs font-semibold text-neutral-500">
        適用済み({applied.length}件)
      </h3>
      {applied.map((e) => (
        <div
          key={e.id}
          data-testid={`applied-${e.id}`}
          className="flex items-center gap-2 border-b border-neutral-100 px-3 py-2 dark:border-neutral-800"
        >
          <DiffText edit={e} />
          <span className="text-xs text-neutral-400">
            {e.created_by === 'assist' ? 'アシスト' : e.confidence === 'auto' ? '自動' : '承認'}
          </span>
          <Button
            variant="ghost"
            className="ml-auto !px-2 !py-0.5 text-xs"
            onClick={() => revert.mutate(e.id)}
          >
            取り消し
          </Button>
        </div>
      ))}
    </div>
  )
}
