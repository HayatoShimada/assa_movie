/**
 * セグメント一覧(仮想スクロール)。
 * クリックで動画シーク、再生位置に追従してハイライト、相槌はグレー表示。
 */
import { useVirtualizer } from '@tanstack/react-virtual'
import { useEffect, useRef } from 'react'
import type { Segment } from '../../api/client'
import { usePlayback } from '../../stores/playback'
import { SpeakerBadge, formatTime } from '../ui'

export function SegmentList({ segments }: { segments: Segment[] }) {
  const parentRef = useRef<HTMLDivElement>(null)
  const currentTime = usePlayback((s) => s.currentTime)
  const seekTo = usePlayback((s) => s.seekTo)
  const selectedId = usePlayback((s) => s.selectedSegmentId)
  const selectSegment = usePlayback((s) => s.selectSegment)
  // ユーザーがリストを触っている間は自動追従スクロールを止める
  const userScrolling = useRef(false)
  const scrollTimer = useRef<number>(0)

  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 56,
    overscan: 10,
  })

  const activeIndex = segments.findIndex((s) => s.start <= currentTime && currentTime < s.end)

  useEffect(() => {
    if (activeIndex >= 0 && !userScrolling.current) {
      virtualizer.scrollToIndex(activeIndex, { align: 'center' })
    }
  }, [activeIndex, virtualizer])

  return (
    <div
      ref={parentRef}
      data-testid="segment-list"
      className="h-full overflow-y-auto"
      onWheel={() => {
        userScrolling.current = true
        window.clearTimeout(scrollTimer.current)
        scrollTimer.current = window.setTimeout(() => (userScrolling.current = false), 3000)
      }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((row) => {
          const seg = segments[row.index]
          const isActive = row.index === activeIndex
          const isSelected = seg.id === selectedId
          return (
            <button
              key={seg.id}
              type="button"
              data-testid={`segment-${seg.idx}`}
              data-active={isActive || undefined}
              onClick={() => {
                selectSegment(seg.id)
                seekTo(seg.start)
              }}
              className={[
                'absolute left-0 flex w-full items-start gap-2 border-b border-neutral-100 px-3 py-2 text-left text-sm dark:border-neutral-800',
                isActive ? 'bg-blue-50 dark:bg-blue-950' : 'hover:bg-neutral-50 dark:hover:bg-neutral-900',
                isSelected ? 'ring-1 ring-inset ring-blue-400' : '',
                seg.is_aizuchi ? 'opacity-40' : '',
              ].join(' ')}
              style={{ top: row.start, height: row.size }}
              ref={virtualizer.measureElement}
              data-index={row.index}
            >
              <span className="w-12 shrink-0 pt-0.5 font-mono text-xs text-neutral-400">
                {formatTime(seg.start)}
              </span>
              {seg.speaker && <SpeakerBadge name={seg.speaker} />}
              <span className="min-w-0 flex-1 break-words">
                {seg.text.replace(/^[^:]+: /, '')}
                {seg.edited_by_user && (
                  <span className="ml-1 align-middle text-xs text-amber-600">(編集済)</span>
                )}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
