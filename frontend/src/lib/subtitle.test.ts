import { describe, expect, it } from 'vitest'
import { wrapSubtitle } from './subtitle'

// ケース表はバックエンドと共有する(tests/fixtures/subtitle_wrap_cases.json)。
// 手でコピーしていた頃は Python 25件 / TS 15件と気付かないうちに乖離しており、
// 片方だけケースを足しても、もう片方の実装がずれたことに気付けなかった。
import fixture from '../../../tests/fixtures/subtitle_wrap_cases.json'

const CASES = fixture.cases as [string, number, string[]][]

describe('wrapSubtitle(バックエンドと同一ケース)', () => {
  it('ケース表を読めている', () => {
    expect(CASES.length).toBeGreaterThan(20)
  })

  it.each(CASES)('%s (max=%d)', (text, maxChars, expected) => {
    expect(wrapSubtitle(text, maxChars)).toEqual(expected)
  })
})
