import { describe, expect, it } from 'vitest'
import { timelineWindow } from './clipTimeline'

describe('timelineWindow(クリップ範囲バーの表示窓)', () => {
  it.each([
    // [開始, 終了, 動画の長さ, 窓の開始, 窓の終了]
    // 前後に余白(範囲の20%、最低5秒)を持たせる
    [30, 50, 120, 25, 55],
    [100, 200, 600, 80, 220],
    // 動画の頭より前には広げない
    [2, 20, 120, 0, 25],
    // 動画の終わりより後ろにも広げない(1:02の動画で終端が1:04と出ていた)
    [40, 59, 62, 35, 62],
    // 長さが分からないときは余白をそのまま付ける
    [40, 59, null, 35, 64],
    // 範囲が動画の長さを超えて保存されていても、範囲そのものは見せる
    [40, 70, 62, 34, 70],
  ] as const)('%s〜%s秒(全体%s秒) → %s〜%s秒', (start, end, duration, viewStart, viewEnd) => {
    expect(timelineWindow(start, end, duration)).toEqual({ viewStart, viewEnd })
  })
})
