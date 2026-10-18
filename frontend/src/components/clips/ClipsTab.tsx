/** クリップタブ: 候補生成 → カード一覧 → クリップ編集(トリム・中抜き・メタ・書き出し)。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { clipsApi, type Clip } from '../../api/clips'
import { useTrackedJob } from '../../hooks/useTrackedJob'
import { CONVERT_METHOD_LABELS } from '../../lib/catalogs'
import { jobSlots } from '../../lib/jobs'
import { clipStatusLabel } from '../../lib/media'
import type { SettingsValues } from '../../lib/settings'
import { ExportResult } from '../export/ExportResult'
import { TrashIcon } from '../icons'
import { usePlayback } from '../../stores/playback'
import { JobStatus } from '../JobStatus'
import { Button, formatTime } from '../ui'
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

const POSITION_LABELS: Record<Clip['subtitle_position'], string> = {
  top: '上',
  center: '中央',
  bottom: '下',
}

const inputCls =
  'w-full rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900'

function ClipEditor({
  clip,
  mediaId,
  duration,
  defaultSubtitlePosition,
  defaultSubtitleOffsetY,
}: {
  clip: Clip
  mediaId: number
  /** 動画の長さ(秒)。範囲バーを動画の終わりより後ろへ広げないため */
  duration: number | null
  /** プロジェクト設定(未設定なら全体設定)の字幕位置 */
  defaultSubtitlePosition: Clip['subtitle_position']
  defaultSubtitleOffsetY: number
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

  // ジョブIDはクリップごとにタブの外へ預ける(タブ切替・クリップの選び直し・
  // 再読み込みで進捗を失わない。lib/jobs.ts)
  const resolveJob = useTrackedJob(jobSlots.clipResolve(mediaId, clip.id), () => {
    queryClient.invalidateQueries({ queryKey: ['segments'] })
    queryClient.invalidateQueries({ queryKey: ['edits'] })
  })
  const resolve = useMutation({
    mutationFn: () => clipsApi.resolve(clip.id),
    onSuccess: (r) => resolveJob.start(r.job_id),
  })

  const metaJob = useTrackedJob(jobSlots.clipMeta(mediaId, clip.id), invalidate)
  const meta = useMutation({
    mutationFn: () => clipsApi.meta(mediaId, clip.id),
    onSuccess: (job) => metaJob.start(job.id),
  })

  const [resultPath, setResultPath] = useState<string | null>(null)
  const exportJob = useTrackedJob(jobSlots.clipExport(mediaId, clip.id), async (job) => {
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
      exportJob.start(r.job_id)
    },
  })

  const dur = effectiveDuration(clip)
  const target = clip.target_duration

  return (
    <div className="space-y-3 border-t border-neutral-200 p-3 dark:border-neutral-800">
      <ClipTimeline
        clip={clip}
        duration={duration}
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
        <Button
          variant="ghost"
          onClick={() => resolve.mutate()}
          disabled={resolve.isPending || resolveJob.busy}
        >
          指示語を自己完結化
        </Button>
        <Button
          variant="ghost"
          onClick={() => meta.mutate()}
          disabled={meta.isPending || metaJob.busy}
        >
          タイトル・メタ生成
        </Button>
        <Button
          data-testid="clip-export"
          onClick={() => exportRun.mutate()}
          disabled={exportRun.isPending || exportJob.busy}
        >
          書き出し
        </Button>
      </div>

      <JobStatus
        progress={resolveJob.progress}
        running="解決中"
        done="自己完結化完了(レビュータブで確認)"
        data-testid="clip-resolve-status"
      />
      <JobStatus
        progress={metaJob.progress}
        running="タイトル・メタを生成中"
        done="タイトル・メタ生成完了"
        data-testid="clip-meta-status"
      />
      <JobStatus
        progress={exportJob.progress}
        running="書き出し中"
        done="書き出し完了"
        data-testid="clip-export-status"
      />
      {exportJob.jobId !== null && resultPath && (
        <ExportResult jobId={exportJob.jobId} path={resultPath} testId="clip-export-result" />
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
          {Object.entries(CONVERT_METHOD_LABELS).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
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
        <div className="flex items-center justify-between gap-2">
          <label htmlFor={`clip-${clip.id}-subtitle-position`} className="block text-xs text-neutral-500">
            字幕位置(このクリップだけ)
          </label>
          {/* クリップの字幕位置を、プロジェクト設定(未設定なら全体設定)の値へ戻す。
              以前の「全体設定で上書き」は、全体設定を書き換えるのか戻すのか読めなかった */}
          <Button
            type="button"
            variant="ghost"
            data-testid="clip-subtitle-reset"
            title="字幕位置と上下微調整を、プロジェクト設定(未設定なら全体設定)の値に戻します"
            disabled={
              clip.subtitle_position === defaultSubtitlePosition &&
              clip.subtitle_offset_y === defaultSubtitleOffsetY
            }
            onClick={() =>
              update.mutate({
                subtitle_position: defaultSubtitlePosition,
                subtitle_offset_y: defaultSubtitleOffsetY,
              })
            }
          >
            既定の位置に戻す({POSITION_LABELS[defaultSubtitlePosition]}・{defaultSubtitleOffsetY}px)
          </Button>
        </div>
        <select
          id={`clip-${clip.id}-subtitle-position`}
          data-testid="clip-subtitle-position"
          className={inputCls}
          value={clip.subtitle_position}
          onChange={(e) => update.mutate({ subtitle_position: e.target.value as Clip['subtitle_position'] })}
        >
          {Object.entries(POSITION_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
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
        {/* タイトルとフックは投稿用のメモ。書き出す動画には焼き込まない */}
        <label className="block pt-1 text-xs text-neutral-500">
          タイトル(一覧での名前・投稿用。動画には入りません)
          <input
            data-testid="clip-title"
            className={`mt-0.5 ${inputCls} text-neutral-900 dark:text-neutral-100`}
            placeholder="例: ハッカソンで見つけた答え"
            defaultValue={clip.title ?? ''}
            onBlur={(e) =>
              e.target.value !== (clip.title ?? '') && update.mutate({ title: e.target.value })
            }
          />
        </label>
        <label className="block text-xs text-neutral-500">
          フック(投稿時に冒頭へ載せるテロップ案。動画には入りません)
          <input
            data-testid="clip-hook"
            className={`mt-0.5 ${inputCls} text-neutral-900 dark:text-neutral-100`}
            placeholder="例: 去年の意外な挑戦"
            defaultValue={clip.hook_text ?? ''}
            onBlur={(e) =>
              e.target.value !== (clip.hook_text ?? '') &&
              update.mutate({ hook_text: e.target.value })
            }
          />
        </label>
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
  styleValues,
  onSelectedClipChange,
}: {
  mediaId: number
  /** プロジェクト設定を反映済みの設定値(lib/settings.ts の resolveSettings) */
  styleValues: SettingsValues
  /** プレビュー用に選択中のクリップを親へ通知する */
  onSelectedClipChange?: (clip: Clip | null) => void
}) {
  const queryClient = useQueryClient()
  const clips = useQuery({ queryKey: ['clips', mediaId], queryFn: () => clipsApi.list(mediaId) })
  const media = useQuery({ queryKey: ['mediaItem', mediaId], queryFn: () => api.getMedia(mediaId) })
  const [target, setTarget] = useState(60)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // ジョブIDはタブの外に預ける(タブ切替・再読み込みで進捗を失わない)
  const { progress, busy, start } = useTrackedJob(jobSlots.suggestClips(mediaId), () =>
    queryClient.invalidateQueries({ queryKey: ['clips', mediaId] }),
  )
  const suggest = useMutation({
    mutationFn: () => clipsApi.suggest(mediaId, target || undefined),
    onSuccess: (job) => start(job.id),
  })
  const remove = useMutation({
    mutationFn: (id: number) => clipsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clips', mediaId] }),
  })

  const running = busy || suggest.isPending
  const selected = clips.data?.find((c) => c.id === selectedId)
  // 3層設定: クリップの値 > プロジェクト設定 > 全体設定。戻す先はプロジェクト(解決済み)
  const defaultSubtitlePosition =
    (styleValues.subtitle_position as Clip['subtitle_position'] | undefined) ?? 'bottom'
  const defaultSubtitleOffsetY = Number(styleValues.subtitle_offset_y ?? 0)

  useEffect(() => {
    onSelectedClipChange?.(selected ?? null)
  }, [onSelectedClipChange, selected])

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
        <JobStatus
          progress={progress}
          running="候補を探索中"
          done="候補生成完了"
          data-testid="suggest-status"
        />
      </div>

      {clips.data?.length === 0 && (
        <p className="p-3 text-sm text-neutral-500">
          候補がまだありません。「切り抜き候補を探す」を実行してください。
        </p>
      )}
      {clips.data?.map((clip) => (
        <div key={clip.id}>
          {/* 選択と削除は別々のボタンにする(入れ子のボタンは押し分けが壊れるため) */}
          <div
            className={`flex items-start gap-1 border-b border-neutral-100 pr-2 dark:border-neutral-800 ${
              selectedId === clip.id ? 'bg-blue-50 dark:bg-blue-950' : ''
            }`}
          >
            <button
              type="button"
              data-testid={`clip-${clip.id}`}
              onClick={() => setSelectedId(selectedId === clip.id ? null : clip.id)}
              className="min-w-0 flex-1 cursor-pointer p-3 text-left text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
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
              </div>
              {clip.hook_text && (
                <p className="mt-0.5 text-xs text-neutral-500">「{clip.hook_text}」</p>
              )}
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
                  {clipStatusLabel(clip.status)}
                </span>
              </div>
            </button>
            <button
              type="button"
              data-testid={`clip-delete-${clip.id}`}
              title="このクリップを削除"
              aria-label="このクリップを削除"
              disabled={remove.isPending}
              onClick={() => remove.mutate(clip.id)}
              className="mt-2 rounded p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-40 dark:hover:bg-red-950"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
          {selected?.id === clip.id && (
            <ClipEditor
              clip={selected}
              mediaId={mediaId}
              duration={media.data?.duration ?? null}
              defaultSubtitlePosition={defaultSubtitlePosition}
              defaultSubtitleOffsetY={defaultSubtitleOffsetY}
            />
          )}
        </div>
      ))}
    </div>
  )
}
