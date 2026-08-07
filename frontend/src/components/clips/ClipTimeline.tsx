/**
 * マウス操作のクリップ範囲バー。
 * - 両端ハンドルをドラッグして開始/終了を調整(0.1秒単位)
 * - 中抜き区間は斜線帯で表示し、クリックでON/OFF
 * - 表示窓はクリップ範囲の前後に余白を持たせる
 */
import { useCallback, useRef } from 'react'
import type { Clip } from '../../api/clips'
import { formatTime } from '../ui'

const PAD_RATIO = 0.2

export function ClipTimeline({
  clip,
  onRangeChange,
  onToggleCut,
}: {
  clip: Clip
  onRangeChange: (start: number, end: number) => void
  onToggleCut: (cutId: number, active: boolean) => void
}) {
  const trackRef = useRef<HTMLDivElement>(null)
  const drag = useRef<'start' | 'end' | null>(null)
  // ドラッグ中の値(確定はpointerup時にonRangeChangeへ)
  const live = useRef({ start: clip.start, end: clip.end })

  const span = clip.end - clip.start
  const pad = Math.max(5, span * PAD_RATIO)
  const viewStart = Math.max(0, clip.start - pad)
  const viewEnd = clip.end + pad
  const toPct = (t: number) => ((t - viewStart) / (viewEnd - viewStart)) * 100
  const fromClientX = useCallback(
    (clientX: number) => {
      const rect = trackRef.current!.getBoundingClientRect()
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
      return viewStart + ratio * (viewEnd - viewStart)
    },
    [viewStart, viewEnd],
  )

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!drag.current) return
      const t = Math.round(fromClientX(e.clientX) * 10) / 10
      if (drag.current === 'start') live.current.start = Math.min(t, live.current.end - 1)
      else live.current.end = Math.max(t, live.current.start + 1)
      // ドラッグ中はDOMを直接動かす(再レンダリングなしで滑らかに)
      const el = trackRef.current!
      const startEl = el.querySelector<HTMLElement>('[data-handle=start]')!
      const rangeEl = el.querySelector<HTMLElement>('[data-handle=range]')!
      const endEl = el.querySelector<HTMLElement>('[data-handle=end]')!
      startEl.style.left = `${toPct(live.current.start)}%`
      endEl.style.left = `${toPct(live.current.end)}%`
      rangeEl.style.left = `${toPct(live.current.start)}%`
      rangeEl.style.width = `${toPct(live.current.end) - toPct(live.current.start)}%`
    },
    [fromClientX, toPct],
  )

  const stopDrag = useCallback(() => {
    if (!drag.current) return
    drag.current = null
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', stopDrag)
    onRangeChange(live.current.start, live.current.end)
  }, [onPointerMove, onRangeChange])

  const startDrag = (which: 'start' | 'end') => (e: React.PointerEvent) => {
    e.preventDefault()
    drag.current = which
    live.current = { start: clip.start, end: clip.end }
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', stopDrag)
  }

  return (
    <div className="select-none">
      <div className="mb-1 flex justify-between font-mono text-xs text-neutral-400">
        <span>{formatTime(viewStart)}</span>
        <span>{formatTime(viewEnd)}</span>
      </div>
      <div
        ref={trackRef}
        data-testid="clip-timeline"
        className="relative h-10 rounded bg-neutral-200 dark:bg-neutral-800"
      >
        {/* クリップ範囲 */}
        <div
          data-handle="range"
          className="absolute top-0 h-full bg-blue-200 dark:bg-blue-900"
          style={{ left: `${toPct(clip.start)}%`, width: `${toPct(clip.end) - toPct(clip.start)}%` }}
        />
        {/* 中抜き区間(クリックでON/OFF) */}
        {clip.cuts.map((cut) => (
          <button
            key={cut.id}
            type="button"
            title={`${cut.source === 'silence' ? '無音' : cut.source === 'aizuchi' ? '相槌' : '手動'} ${
              cut.active ? '(中抜き有効・クリックで戻す)' : '(無効・クリックで中抜き)'
            }`}
            data-testid={`cut-${cut.id}`}
            onClick={() => onToggleCut(cut.id, !cut.active)}
            className={`absolute top-1 h-8 rounded-sm border ${
              cut.active
                ? 'border-red-400 bg-red-300/70 dark:bg-red-800/70'
                : 'border-neutral-400 bg-neutral-300/40 dark:bg-neutral-600/40'
            }`}
            style={{
              left: `${toPct(cut.start)}%`,
              width: `${Math.max(0.5, toPct(cut.end) - toPct(cut.start))}%`,
              backgroundImage: cut.active
                ? 'repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(255,255,255,.5) 3px, rgba(255,255,255,.5) 6px)'
                : undefined,
            }}
          />
        ))}
        {/* ドラッグハンドル */}
        <div
          data-handle="start"
          data-testid="handle-start"
          onPointerDown={startDrag('start')}
          className="absolute top-0 h-full w-2 -translate-x-1/2 cursor-ew-resize rounded bg-blue-600"
          style={{ left: `${toPct(clip.start)}%` }}
        />
        <div
          data-handle="end"
          data-testid="handle-end"
          onPointerDown={startDrag('end')}
          className="absolute top-0 h-full w-2 -translate-x-1/2 cursor-ew-resize rounded bg-blue-600"
          style={{ left: `${toPct(clip.end)}%` }}
        />
      </div>
    </div>
  )
}
