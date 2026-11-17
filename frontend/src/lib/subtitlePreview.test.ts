import { describe, expect, it } from 'vitest'
import { activeEvent, previewQuery, previewSignature, upcomingKeys } from './subtitlePreview'

const ev = (start: number, end: number, key: string) => ({ start, end, key, text: key })
const EVENTS = [ev(1, 2, 'a'), ev(2, 4, 'b'), ev(10, 12, 'a'), ev(12, 13, 'c')]

describe('previewQuery', () => {
  it.each([
    ['何も無ければ空', {}, ''],
    ['クリップの位置', { position: 'top' as const, offsetY: -60 }, '?position=top&offset_y=-60'],
    ['ずらし0は有効な値として送る', { position: 'bottom' as const, offsetY: 0 }, '?position=bottom&offset_y=0'],
    ['null は送らない(設定の値を使わせる)', { position: null, offsetY: null }, ''],
    ['クリップの範囲', { start: 0, end: 8.5 }, '?start=0&end=8.5'],
  ])('%s', (_name, params, expected) => {
    expect(previewQuery(params)).toBe(expected)
  })
})

describe('activeEvent', () => {
  it.each([
    ['最初の字幕より前', 0.5, undefined],
    ['開始ちょうどは出す', 1, 'a'],
    ['終了ちょうどは次の字幕', 2, 'b'],
    ['途中', 3.9, 'b'],
    ['字幕の無い区間', 5, undefined],
    ['同じ画像を使う別の字幕', 11, 'a'],
    ['最後の字幕の後', 13, undefined],
  ])('%s', (_name, t, key) => {
    expect(activeEvent(EVENTS, t)?.key).toBe(key)
  })

  it('空の時刻表', () => {
    expect(activeEvent([], 1)).toBeUndefined()
  })
})

describe('upcomingKeys', () => {
  it('今の字幕とこの後の字幕を、重複なしで返す', () => {
    expect(upcomingKeys(EVENTS, 0, 4)).toEqual(['a', 'b', 'c'])
    expect(upcomingKeys(EVENTS, 3, 2)).toEqual(['b', 'a'])
  })

  it('終わった字幕は読まない', () => {
    expect(upcomingKeys(EVENTS, 12.5, 4)).toEqual(['c'])
    expect(upcomingKeys(EVENTS, 99, 4)).toEqual([])
  })
})

describe('previewSignature', () => {
  const base = { subtitle_font_size: 48, subtitle_bg: 'none', filler_level: 'off', asr_model: 'large-v3' }

  it('字幕に効く設定が変わると変わる', () => {
    expect(previewSignature({ ...base, subtitle_font_size: 64 })).not.toBe(previewSignature(base))
    expect(previewSignature({ ...base, filler_level: 'weak' })).not.toBe(previewSignature(base))
  })

  it('字幕に関係ない設定では変わらない(取り直さない)', () => {
    expect(previewSignature({ ...base, asr_model: 'large-v3-turbo' })).toBe(previewSignature(base))
  })

  it('キーの順番に依らない', () => {
    expect(previewSignature({ filler_level: 'off', subtitle_bg: 'none' })).toBe(
      previewSignature({ subtitle_bg: 'none', filler_level: 'off' }),
    )
  })
})
