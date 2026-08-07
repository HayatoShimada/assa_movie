/** エディタ: 動画プレビュー + 右パネル(トランスクリプト / 設定)。 */
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { VideoPlayer } from '../components/player/VideoPlayer'
import { SegmentList } from '../components/transcript/SegmentList'
import { SettingsForm } from '../components/settings/SettingsForm'
import { Button } from '../components/ui'
import { navigate } from '../hooks/useHashRoute'

type Tab = 'transcript' | 'settings'

export function Editor({ mediaId }: { mediaId: number }) {
  const [tab, setTab] = useState<Tab>('transcript')
  const [showAizuchi, setShowAizuchi] = useState(true)

  const media = useQuery({
    queryKey: ['mediaItem', mediaId],
    queryFn: () => api.getMedia(mediaId),
  })
  const segments = useQuery({
    queryKey: ['segments', mediaId, showAizuchi],
    queryFn: () => api.listSegments(mediaId, showAizuchi),
  })

  const tabs: { key: Tab; label: string }[] = [
    { key: 'transcript', label: 'トランスクリプト' },
    { key: 'settings', label: '設定' },
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

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_420px]">
        <section className="min-w-0 p-4">
          <VideoPlayer mediaId={mediaId} segments={segments.data ?? []} />
        </section>

        <aside className="flex min-h-0 flex-col border-t border-neutral-200 lg:border-l lg:border-t-0 dark:border-neutral-800">
          <nav className="flex items-center border-b border-neutral-200 dark:border-neutral-800">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`px-4 py-2 text-sm ${
                  tab === t.key
                    ? 'border-b-2 border-blue-600 font-semibold'
                    : 'text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200'
                }`}
              >
                {t.label}
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

          <div className="min-h-0 flex-1">
            {tab === 'transcript' &&
              (segments.data?.length ? (
                <SegmentList segments={segments.data} />
              ) : (
                <p className="p-4 text-sm text-neutral-500">
                  {segments.isPending ? '読み込み中...' : 'セグメントがありません。文字起こしを実行してください。'}
                </p>
              ))}
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
