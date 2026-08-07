/** クリップタブ: 候補生成 → カード一覧 → クリップ編集(トリム・中抜き・メタ・書き出し)。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { clipsApi, type Clip } from '../../api/clips'
import { useJobProgress } from '../../hooks/useJobProgress'
import { usePlayback } from '../../stores/playback'
import { Button, ProgressBar, formatTime } from '../ui'
import { ClipTimeline } from './ClipTimeline'

const TARGETS = [
  { label: 'Shorts (60秒)', value: 60 },
  { label: 'TikTok (30秒)', value: 30 },
  { label: '長め (90秒)', value: 90 },
  { label: '指定なし', value: 0 },
]

function effectiveDuration(clip: Clip): number {
  const cutTotal = clip.cuts
    .filter((c) => c.active)
    .reduce((sum, c) => sum + (Math.min(c.end, clip.end) - Math.max(c.start, clip.start)), 0)
  return clip.end - clip.start - cutTotal
}

function ClipEditor({
  clip,
  mediaId,
  globalSubtitlePosition,
  globalSubtitleOffsetY,
}: {
  clip: Clip
  mediaId: number
  globalSubtitlePosition: Clip['subtitle_position']
  globalSubtitleOffsetY: number
}) {
  const queryClient = useQueryClient()
  const seekTo = usePlayback((s) => s.seekTo)
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['clips', mediaId] })

  const update = useMutation({
    mutationFn: (patch: Parameters<typeof clipsApi.update>[1]) =>
      clipsApi.update(clip.id, patch),
    onSuccess: invalidate,
  })
  const jetcut = useMutation({ mutationFn: () => clipsApi.jetcut(clip.id), onSuccess: invalidate })
  const toggleCut = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      clipsApi.toggleCut(id, active),
    onSuccess: invalidate,
  })

  const [resolveJobId, setResolveJobId] = useState<number | null>(null)
  const resolveProgress = useJobProgress(resolveJobId, () => {
    queryClient.invalidateQueries({ queryKey: ['segments'] })
    queryClient.invalidateQueries({ queryKey: ['edits'] })
  })
  const resolve = useMutation({
    mutationFn: () => clipsApi.resolve(clip.id),
    onSuccess: (r) => setResolveJobId(r.job_id),
  })

  const [metaJobId, setMetaJobId] = useState<number | null>(null)
  useJobProgress(metaJobId, invalidate)
  const meta = useMutation({
    mutationFn: () => clipsApi.meta(mediaId, clip.id),
    onSuccess: (job) => setMetaJobId(job.id),
  })

  const [exportJobId, setExportJobId] = useState<number | null>(null)
  const [resultPath, setResultPath] = useState<string | null>(null)
  const exportProgress = useJobProgress(exportJobId, async (job) => {
    invalidate()
    if (job.status === 'completed') {
      const full = await api.getJob(job.id)
      setResultPath((full.result as { path?: string } | null)?.path ?? null)
    }
  })
  const exportRun = useMutation({
    mutationFn: () => clipsApi.exportClip(clip.id),
    onSuccess: (r) => {
      setResultPath(null)
      setExportJobId(r.job_id)
    },
  })

  const dur = effectiveDuration(clip)
  const target = clip.target_duration

  return (
    <div className="space-y-3 border-t border-neutral-200 p-3 dark:border-neutral-800">
      <ClipTimeline
        clip={clip}
        onRangeChange={(start, end) => update.mutate({ start, end })}
        onToggleCut={(id, active) => toggleCut.mutate({ id, active })}
      />

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono">
          {formatTime(clip.start)} 〜 {formatTime(clip.end)}
        </span>
        <span
          data-testid="clip-duration"
          className={`rounded px-2 py-0.5 font-mono text-xs ${
            target && Math.abs(dur - target) <= target * 0.15
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200'
              : 'bg-neutral-100 dark:bg-neutral-800'
          }`}
        >
          実尺 {dur.toFixed(1)}秒{target ? ` / 目標 ${target}秒` : ''}
        </span>
        <button
          type="button"
          className="text-xs text-blue-600 hover:underline"
          onClick={() => seekTo(clip.start)}
        >
          ここから再生
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" onClick={() => jetcut.mutate()} disabled={jetcut.isPending}>
          中抜きを提案
        </Button>
        <Button variant="ghost" onClick={() => resolve.mutate()} disabled={resolve.isPending}>
          指示語を自己完結化
        </Button>
        <Button variant="ghost" onClick={() => meta.mutate()} disabled={meta.isPending}>
          タイトル・メタ生成
        </Button>
        <Button
          data-testid="clip-export"
          onClick={() => exportRun.mutate()}
          disabled={exportProgress.status === 'running'}
        >
          書き出し
        </Button>
      </div>

      {resolveJobId !== null && resolveProgress.status !== 'idle' && (
        <ProgressBar
          value={resolveProgress.progress}
          label={resolveProgress.status === 'completed' ? '自己完結化完了(レビュータブで確認)' : '解決中...'}
        />
      )}
      {exportJobId !== null && exportProgress.status !== 'idle' && (
        <ProgressBar
          value={exportProgress.progress}
          label={
            exportProgress.status === 'failed'
              ? `失敗: ${exportProgress.error?.split('\n')[0]}`
              : exportProgress.status === 'completed'
                ? '書き出し完了'
                : `書き出し中... ${Math.round(exportProgress.progress * 100)}%`
          }
        />
      )}
      {resultPath && (
        <p data-testid="clip-export-result" className="break-all text-xs text-emerald-600">
          出力: {resultPath}
        </p>
      )}

      <div className="space-y-1">
        <label className="block text-xs text-neutral-500">縦横変換(このクリップだけ上書き)</label>
        <select
          data-testid="clip-convert-method"
          className="w-full rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          value={clip.convert_method ?? ''}
          onChange={(e) =>
            update.mutate({
              convert_method: (e.target.value || null) as Clip['convert_method'],
            })
          }
        >
          <option value="">プロジェクト既定</option>
          <option value="crop">中央クロップ(位置調整可)</option>
          <option value="blur_pad">ぼかし背景(全体表示)</option>
          <option value="face">顔検出(1人=追従 / 2人=上下分割)</option>
        </select>
        {clip.convert_method === 'crop' && (
          <>
            <label className="block text-xs text-neutral-500">
              クロップ位置 ({Math.round(clip.crop_x * 100)}%)
            </label>
            <input
              data-testid="clip-crop-x"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={clip.crop_x}
              onChange={(e) => update.mutate({ crop_x: Number(e.target.value) })}
              className="w-full"
            />
          </>
        )}
        <div className="flex items-center justify-between">
          <label className="block text-xs text-neutral-500">字幕位置</label>
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              update.mutate({
                subtitle_position: globalSubtitlePosition,
                subtitle_offset_y: globalSubtitleOffsetY,
              })
            }
          >
            全体設定で上書き
          </Button>
        </div>
        <select
          data-testid="clip-subtitle-position"
          className="w-full rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          value={clip.subtitle_position}
          onChange={(e) => update.mutate({ subtitle_position: e.target.value as Clip['subtitle_position'] })}
        >
          <option value="top">上</option>
          <option value="center">中央</option>
          <option value="bottom">下</option>
        </select>
        <label className="block text-xs text-neutral-500">上下微調整 ({clip.subtitle_offset_y}px)</label>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => update.mutate({ subtitle_offset_y: Math.max(-120, clip.subtitle_offset_y - 4) })}
          >
            上へ
          </Button>
          <input
            data-testid="clip-subtitle-offset"
            type="range"
            min={-120}
            max={120}
            step={1}
            value={clip.subtitle_offset_y}
            onChange={(e) => update.mutate({ subtitle_offset_y: Number(e.target.value) })}
            className="w-full"
          />
          <Button
            type="button"
            variant="ghost"
            onClick={() => update.mutate({ subtitle_offset_y: Math.min(120, clip.subtitle_offset_y + 4) })}
          >
            下へ
          </Button>
        </div>
        <input
          className="w-full rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="タイトル"
          defaultValue={clip.title ?? ''}
          onBlur={(e) => e.target.value !== (clip.title ?? '') && update.mutate({ title: e.target.value })}
        />
        <input
          className="w-full rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="フックテキスト(冒頭テロップ)"
          defaultValue={clip.hook_text ?? ''}
          onBlur={(e) =>
            e.target.value !== (clip.hook_text ?? '') && update.mutate({ hook_text: e.target.value })
          }
        />
        {clip.meta && (
          <div className="rounded border border-neutral-200 p-2 text-xs dark:border-neutral-700">
            {clip.meta.hooks.length > 0 && (
              <p>
                フック案:{' '}
                {clip.meta.hooks.map((h) => (
                  <button
                    key={h}
                    type="button"
                    className="mr-1 rounded bg-neutral-100 px-1.5 py-0.5 hover:bg-blue-100 dark:bg-neutral-800 dark:hover:bg-blue-900"
                    onClick={() => update.mutate({ hook_text: h })}
                  >
                    {h}
                  </button>
                ))}
              </p>
            )}
            <p className="mt-1 text-neutral-500">{clip.meta.description}</p>
            <p className="mt-0.5 text-blue-600">{clip.meta.hashtags.join(' ')}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export function ClipsTab({
  mediaId,
  onSubtitlePositionPreviewChange,
  onSubtitleOffsetPreviewChange,
  onConvertPreviewChange,
}: {
  mediaId: number
  onSubtitlePositionPreviewChange?: (position: Clip['subtitle_position'] | null) => void
  onSubtitleOffsetPreviewChange?: (offsetY: number | null) => void
  onConvertPreviewChange?: (method: Clip['convert_method'], cropX: number | null) => void
}) {
  const queryClient = useQueryClient()
  const clips = useQuery({ queryKey: ['clips', mediaId], queryFn: () => clipsApi.list(mediaId) })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const [target, setTarget] = useState(60)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const progress = useJobProgress(jobId, () =>
    queryClient.invalidateQueries({ queryKey: ['clips', mediaId] }),
  )
  const suggest = useMutation({
    mutationFn: () => clipsApi.suggest(mediaId, target || undefined),
    onSuccess: (job) => setJobId(job.id),
  })
  const remove = useMutation({
    mutationFn: (id: number) => clipsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clips', mediaId] }),
  })

  const running = progress.status === 'running' || progress.status === 'queued'
  const selected = clips.data?.find((c) => c.id === selectedId)
  const globalSubtitlePosition =
    (settings.data?.values.subtitle_position as Clip['subtitle_position'] | undefined) ?? 'bottom'
  const globalSubtitleOffsetY = Number(settings.data?.values.subtitle_offset_y ?? 0)

  useEffect(() => {
    onSubtitlePositionPreviewChange?.(selected?.subtitle_position ?? null)
    onSubtitleOffsetPreviewChange?.(selected?.subtitle_offset_y ?? null)
    onConvertPreviewChange?.(selected?.convert_method ?? null, selected?.crop_x ?? null)
  }, [
    onConvertPreviewChange,
    onSubtitleOffsetPreviewChange,
    onSubtitlePositionPreviewChange,
    selected?.convert_method,
    selected?.crop_x,
    selected?.subtitle_offset_y,
    selected?.subtitle_position,
  ])

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="space-y-2 border-b border-neutral-200 p-3 dark:border-neutral-800">
        <div className="flex items-center gap-2">
          <select
            data-testid="clip-target"
            className="rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={target}
            onChange={(e) => setTarget(Number(e.target.value))}
          >
            {TARGETS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <Button data-testid="run-suggest" disabled={running} onClick={() => suggest.mutate()}>
            切り抜き候補を探す
          </Button>
        </div>
        {jobId !== null && progress.status !== 'idle' && (
          <ProgressBar
            value={progress.progress}
            label={progress.status === 'completed' ? '候補生成完了' : '候補を探索中...'}
          />
        )}
      </div>

      {clips.data?.length === 0 && (
        <p className="p-3 text-sm text-neutral-500">
          候補がまだありません。「切り抜き候補を探す」を実行してください。
        </p>
      )}
      {clips.data?.map((clip) => (
        <div key={clip.id}>
          <div
            role="button"
            tabIndex={0}
            data-testid={`clip-${clip.id}`}
            onClick={() => setSelectedId(selectedId === clip.id ? null : clip.id)}
            onKeyDown={(e) => e.key === 'Enter' && setSelectedId(selectedId === clip.id ? null : clip.id)}
            className={`w-full cursor-pointer border-b border-neutral-100 p-3 text-left text-sm hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900 ${
              selectedId === clip.id ? 'bg-blue-50 dark:bg-blue-950' : ''
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="font-medium">{clip.title || '(無題)'}</span>
              {clip.score != null && (
                <span className="rounded bg-amber-100 px-1.5 text-xs text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                  {clip.score.toFixed(1)}
                </span>
              )}
              <span className="ml-auto font-mono text-xs text-neutral-400">
                {formatTime(clip.start)}〜 {Math.round(clip.end - clip.start)}秒
              </span>
              <button
                type="button"
                className="text-xs text-neutral-400 hover:text-red-600"
                onClick={(e) => {
                  e.stopPropagation()
                  remove.mutate(clip.id)
                }}
              >
                削除
              </button>
            </div>
            {clip.hook_text && <p className="mt-0.5 text-xs text-neutral-500">「{clip.hook_text}」</p>}
            <div className="mt-1 flex flex-wrap gap-1">
              {clip.score_reasons.map((r) => (
                <span
                  key={r}
                  className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                >
                  {r}
                </span>
              ))}
              <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-400 dark:bg-neutral-800">
                {clip.status}
              </span>
            </div>
          </div>
          {selected?.id === clip.id && (
            <ClipEditor
              clip={selected}
              mediaId={mediaId}
              globalSubtitlePosition={globalSubtitlePosition}
              globalSubtitleOffsetY={globalSubtitleOffsetY}
            />
          )}
        </div>
      ))}
    </div>
  )
}
