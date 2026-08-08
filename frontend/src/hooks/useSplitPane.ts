/**
 * 左右2ペインの境界をドラッグで動かすためのフック。
 *
 * 幅はピクセルではなく「ウィンドウ幅に対する割合」で持つ。
 * 画面サイズが変わっても見た目の比率が保たれ、保存値も使い回せるため。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'editor.rightPaneRatio'
/** 動画側・パネル側のどちらも潰れないようにする下限(ウィンドウ幅に対する割合) */
export const MIN_RATIO = 0.2
export const MAX_RATIO = 0.7
export const DEFAULT_RATIO = 0.34

export function clampRatio(ratio: number): number {
  if (!Number.isFinite(ratio)) return DEFAULT_RATIO
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio))
}

/** 境界のx座標(px)から右ペインの割合を出す */
export function ratioFromPointer(clientX: number, windowWidth: number): number {
  if (windowWidth <= 0) return DEFAULT_RATIO
  return clampRatio((windowWidth - clientX) / windowWidth)
}

function loadRatio(): number {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    return saved ? clampRatio(Number(saved)) : DEFAULT_RATIO
  } catch {
    return DEFAULT_RATIO
  }
}

export function useSplitPane() {
  const [ratio, setRatio] = useState<number>(loadRatio)
  const [dragging, setDragging] = useState(false)
  const draggingRef = useRef(false)

  const apply = useCallback((next: number) => {
    setRatio(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, String(next))
    } catch {
      // プライベートモード等で保存できなくても操作自体は続けられる
    }
  }, [])

  useEffect(() => {
    if (!dragging) return
    const onMove = (e: PointerEvent) => {
      if (!draggingRef.current) return
      e.preventDefault()
      apply(ratioFromPointer(e.clientX, window.innerWidth))
    }
    const stop = () => {
      draggingRef.current = false
      setDragging(false)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
  }, [dragging, apply])

  const startDrag = useCallback(() => {
    draggingRef.current = true
    setDragging(true)
  }, [])

  /** キーボードでも動かせるようにする(アクセシビリティ) */
  const nudge = useCallback(
    (delta: number) => apply(clampRatio(ratio + delta)),
    [ratio, apply],
  )

  return { ratio, dragging, startDrag, nudge, reset: () => apply(DEFAULT_RATIO) }
}
