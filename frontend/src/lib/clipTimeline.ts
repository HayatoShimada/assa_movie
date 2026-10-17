/**
 * クリップ範囲バー(components/clips/ClipTimeline.tsx)の表示窓。
 *
 * 範囲の前後に余白を持たせて、ハンドルを外側へ広げられるようにする。
 * ただし動画の頭より前・終わりより後ろには広げない(終端が動画の長さより
 * 後ろの時刻を指し、「1:02の動画なのに1:04まである」と見えていた)。
 */
const PAD_RATIO = 0.2
const MIN_PAD = 5

export function timelineWindow(
  start: number,
  end: number,
  duration: number | null | undefined,
): { viewStart: number; viewEnd: number } {
  const pad = Math.max(MIN_PAD, (end - start) * PAD_RATIO)
  const viewStart = Math.max(0, start - pad)
  const padded = end + pad
  const viewEnd = duration ? Math.max(end, Math.min(duration, padded)) : padded
  return { viewStart, viewEnd }
}
