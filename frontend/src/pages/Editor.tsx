/** エディタ: 動画プレビュー + 右パネル(トランスクリプト / レビュー / 質問 / 設定)。 */
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { Clip } from '../api/clips'
import type { ConvertMethod } from '../lib/catalogs'
import { resolveSettings } from '../lib/settings'
import { VideoPlayer } from '../components/player/VideoPlayer'
import { AssistChat } from '../components/transcript/AssistChat'
import { SegmentList } from '../components/transcript/SegmentList'
import { ClipsTab } from '../components/clips/ClipsTab'
import { ReviewTab } from '../components/edits/ReviewTab'
import { ExportTab } from '../components/export/ExportTab'
import { QuestionsTab } from '../components/questions/QuestionsTab'
import { SettingsForm } from '../components/settings/SettingsForm'
import {
  ClipIcon,
  ExportIcon,
  QuestionIcon,
  ReviewIcon,
  SettingsIcon,
  TranscriptIcon,
} from '../components/icons'
import { Button } from '../components/ui'
import { navigate } from '../hooks/useHashRoute'
import { usePlayback } from '../stores/playback'

type Tab = 'transcript' | 'review' | 'questions' | 'clips' | 'export' | 'settings'

/** 未処理件数。アイコンの右上に小さく重ねる */
function Badge({ count }: { count: number }) {
  if (count === 0) return null
  return (
    <span className="absolute -right-1.5 -top-1 min-w-4 rounded-full bg-blue-600 px-1 text-[10px] font-semibold leading-4 text-white">
      {count > 99 ? '99+' : count}
    </span>
  )
}

export function Editor({ mediaId }: { mediaId: number }) {
  const [tab, setTab] = useState<Tab>('transcript')
  const [showAizuchi, setShowAizuchi] = useState(true)
  // プレビュー対象のクリップ。個々のフィールドではなくクリップごと持つことで
  // 「同じクリップの値である」ことが構造的に保証される
  const [selectedClip, setSelectedClip] = useState<Clip | null>(null)
  const selectedSegmentId = usePlayback((s) => s.selectedSegmentId)

  const media = useQuery({
    queryKey: ['mediaItem', mediaId],
    queryFn: () => api.getMedia(mediaId),
  })
  const project = useQuery({
    queryKey: ['project', media.data?.project_id],
    queryFn: () => api.getProject(media.data!.project_id),
    enabled: media.data?.project_id != null,
  })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const styleValues = resolveSettings(settings.data?.values, project.data?.settings)
  const outputOrientation = project.data?.output_orientation ?? 'landscape'

  const previewClip = tab === 'clips' ? selectedClip : null
  // クリップの上書きが無ければプロジェクト(マージ済み)の変換方式でプレビュー
  const projectConvertMethod = (styleValues.convert_method as ConvertMethod | undefined) ?? null
  const segments = useQuery({
    queryKey: ['segments', mediaId, showAizuchi],
    queryFn: () => api.listSegments(mediaId, showAizuchi),
  })
  const edits = useQuery({
    queryKey: ['edits', mediaId],
    queryFn: () => api.listEdits(mediaId),
  })
  const questions = useQuery({
    queryKey: ['questions', mediaId],
    queryFn: () => api.listQuestions(mediaId),
  })

  const proposedCount = (edits.data ?? []).filter((e) => e.status === 'proposed').length
  const openQuestions = (questions.data ?? []).length
  const selectedSegment = (segments.data ?? []).find((s) => s.id === selectedSegmentId)

  const tabs: {
    key: Tab
    label: string
    badge: number
    Icon: (p: { className?: string }) => React.ReactElement
  }[] = [
    { key: 'transcript', label: '文字起こし', badge: 0, Icon: TranscriptIcon },
    { key: 'review', label: 'レビュー', badge: proposedCount, Icon: ReviewIcon },
    { key: 'questions', label: '質問', badge: openQuestions, Icon: QuestionIcon },
    { key: 'clips', label: 'クリップ', badge: 0, Icon: ClipIcon },
    { key: 'export', label: '書き出し', badge: 0, Icon: ExportIcon },
    { key: 'settings', label: '設定', badge: 0, Icon: SettingsIcon },
  ]

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b border-neutral-200 px-4 py-2 dark:border-neutral-800">
        <Button variant="ghost" onClick={() => navigate({ page: 'home' })}>
          ← 戻る
        </Button>
        <h1 className="truncate text-sm font-semibold">
          {media.data?.path?.split('/').pop() ?? `メディア #${mediaId}`}
        </h1>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_440px]">
        <section className="min-w-0 p-4">
          <VideoPlayer
            mediaId={mediaId}
            segments={segments.data ?? []}
            styleValues={styleValues}
            outputOrientation={outputOrientation}
            subtitlePosition={previewClip?.subtitle_position ?? 'bottom'}
            subtitleOffsetY={previewClip?.subtitle_offset_y ?? 0}
            convertMethod={previewClip ? (previewClip.convert_method ?? projectConvertMethod) : null}
            cropX={previewClip?.crop_x ?? 0.5}
          />
        </section>

        <aside className="flex min-h-0 flex-col border-t border-neutral-200 lg:border-l lg:border-t-0 dark:border-neutral-800">
          <nav className="flex items-center border-b border-neutral-200 dark:border-neutral-800">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                data-testid={`tab-${t.key}`}
                title={t.label}
                aria-label={t.label}
                aria-current={tab === t.key ? 'page' : undefined}
                onClick={() => setTab(t.key)}
                // アイコンの下にラベルを置いて折り返しを防ぐ(横並びだと日本語が2行になる)
                className={`flex flex-1 flex-col items-center gap-0.5 whitespace-nowrap border-b-2 px-1 py-1.5 text-[11px] transition-colors ${
                  tab === t.key
                    ? 'border-blue-600 font-semibold text-blue-700 dark:text-blue-300'
                    : 'border-transparent text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800 dark:hover:bg-neutral-900 dark:hover:text-neutral-200'
                }`}
              >
                <span className="relative">
                  <t.Icon className="h-5 w-5" />
                  <Badge count={t.badge} />
                </span>
                {t.label}
              </button>
            ))}
          </nav>
          {tab === 'transcript' && (
            <label className="flex items-center justify-end gap-1 border-b border-neutral-200 px-3 py-1 text-xs text-neutral-500 dark:border-neutral-800">
              <input
                type="checkbox"
                checked={showAizuchi}
                onChange={(e) => setShowAizuchi(e.target.checked)}
              />
              相槌を表示
            </label>
          )}

          <div className="flex min-h-0 flex-1 flex-col">
            {tab === 'transcript' && (
              <>
                <div className="min-h-0 flex-1">
                  {segments.data?.length ? (
                    <SegmentList segments={segments.data} />
                  ) : (
                    <p className="p-4 text-sm text-neutral-500">
                      {segments.isPending
                        ? '読み込み中...'
                        : 'セグメントがありません。文字起こしを実行してください。'}
                    </p>
                  )}
                </div>
                {selectedSegment && (
                  <AssistChat segment={selectedSegment} projectId={media.data?.project_id} />
                )}
              </>
            )}
            {tab === 'review' && (
              <ReviewTab mediaId={mediaId} projectId={media.data?.project_id} />
            )}
            {tab === 'questions' && <QuestionsTab mediaId={mediaId} />}
            {tab === 'clips' && (
              <ClipsTab mediaId={mediaId} onSelectedClipChange={setSelectedClip} />
            )}
            {tab === 'export' && <ExportTab mediaId={mediaId} />}
            {tab === 'settings' && (
              <div className="h-full overflow-y-auto">
                <SettingsForm />
              </div>
            )}
          </div>
        </aside>
      </div>
    </main>
  )
}
