/** エディタ: 動画プレビュー + 右パネル(トランスクリプト / レビュー / 質問 / 設定)。 */
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { VideoPlayer } from '../components/player/VideoPlayer'
import { AssistChat } from '../components/transcript/AssistChat'
import { SegmentList } from '../components/transcript/SegmentList'
import { ClipsTab } from '../components/clips/ClipsTab'
import { ReviewTab } from '../components/edits/ReviewTab'
import { ExportTab } from '../components/export/ExportTab'
import { QuestionsTab } from '../components/questions/QuestionsTab'
import { SettingsForm } from '../components/settings/SettingsForm'
import { Button } from '../components/ui'
import { navigate } from '../hooks/useHashRoute'
import { usePlayback } from '../stores/playback'

type Tab = 'transcript' | 'review' | 'questions' | 'clips' | 'export' | 'settings'

function Badge({ count }: { count: number }) {
  if (count === 0) return null
  return (
    <span className="ml-1 rounded-full bg-blue-600 px-1.5 text-xs font-semibold text-white">
      {count}
    </span>
  )
}

export function Editor({ mediaId }: { mediaId: number }) {
  const [tab, setTab] = useState<Tab>('transcript')
  const [showAizuchi, setShowAizuchi] = useState(true)
  const [clipSubtitlePosition, setClipSubtitlePosition] = useState<'top' | 'center' | 'bottom' | null>(null)
  const [clipSubtitleOffsetY, setClipSubtitleOffsetY] = useState<number | null>(null)
  const selectedSegmentId = usePlayback((s) => s.selectedSegmentId)

  const media = useQuery({
    queryKey: ['mediaItem', mediaId],
    queryFn: () => api.getMedia(mediaId),
  })
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

  const tabs: { key: Tab; label: string; badge: number }[] = [
    { key: 'transcript', label: 'トランスクリプト', badge: 0 },
    { key: 'review', label: 'レビュー', badge: proposedCount },
    { key: 'questions', label: '質問', badge: openQuestions },
    { key: 'clips', label: 'クリップ', badge: 0 },
    { key: 'export', label: '書き出し', badge: 0 },
    { key: 'settings', label: '設定', badge: 0 },
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
            subtitlePosition={tab === 'clips' ? (clipSubtitlePosition ?? 'bottom') : 'bottom'}
            subtitleOffsetY={tab === 'clips' ? (clipSubtitleOffsetY ?? 0) : 0}
          />
        </section>

        <aside className="flex min-h-0 flex-col border-t border-neutral-200 lg:border-l lg:border-t-0 dark:border-neutral-800">
          <nav className="flex items-center border-b border-neutral-200 dark:border-neutral-800">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                data-testid={`tab-${t.key}`}
                onClick={() => setTab(t.key)}
                className={`px-3 py-2 text-sm ${
                  tab === t.key
                    ? 'border-b-2 border-blue-600 font-semibold'
                    : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
                }`}
              >
                {t.label}
                <Badge count={t.badge} />
              </button>
            ))}
            {tab === 'transcript' && (
              <label className="ml-auto flex items-center gap-1 px-3 text-xs text-neutral-500">
                <input
                  type="checkbox"
                  checked={showAizuchi}
                  onChange={(e) => setShowAizuchi(e.target.checked)}
                />
                相槌を表示
              </label>
            )}
          </nav>

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
              <ClipsTab
                mediaId={mediaId}
                onSubtitlePositionPreviewChange={setClipSubtitlePosition}
                onSubtitleOffsetPreviewChange={setClipSubtitleOffsetY}
              />
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
