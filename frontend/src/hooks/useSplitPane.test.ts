import { describe, expect, it } from 'vitest'
import {
  clampRatio,
  DEFAULT_RATIO,
  MAX_RATIO,
  MIN_RATIO,
  ratioFromPointer,
} from './useSplitPane'

describe('clampRatio', () => {
  it.each([
    [0.5, 0.5],
    [0.01, MIN_RATIO], // 動画側が潰れないよう下限で止める
    [0.99, MAX_RATIO], // パネル側が広がりすぎないよう上限で止める
    [Number.NaN, DEFAULT_RATIO],
  ])('%s → %s', (given, expected) => {
    expect(clampRatio(given)).toBe(expected)
  })
})

describe('ratioFromPointer', () => {
  it('境界を左へ動かすとパネルが広がる', () => {
    expect(ratioFromPointer(700, 1000)).toBeCloseTo(0.3)
    expect(ratioFromPointer(500, 1000)).toBeCloseTo(0.5)
  })

  it('端までドラッグしても下限・上限に収まる', () => {
    expect(ratioFromPointer(1000, 1000)).toBe(MIN_RATIO)
    expect(ratioFromPointer(0, 1000)).toBe(MAX_RATIO)
  })

  it('ウィンドウ幅が取れないときは既定値', () => {
    expect(ratioFromPointer(300, 0)).toBe(DEFAULT_RATIO)
  })
})
