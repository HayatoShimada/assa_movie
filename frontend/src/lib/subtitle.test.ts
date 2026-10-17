import { describe, expect, it } from 'vitest'
import { wrapChars, wrapSubtitle } from './subtitle'

// ケース表はバックエンドと共有する(tests/fixtures/ 以下)。
// 手でコピーしていた頃は Python 25件 / TS 15件と気付かないうちに乖離しており、
// 片方だけケースを足しても、もう片方の実装がずれたことに気付けなかった。
import charFixture from '../../../tests/fixtures/subtitle_wrap_cases.json'
import phraseFixture from '../../../tests/fixtures/subtitle_phrase_wrap_cases.json'

const CHAR_CASES = charFixture.cases as [string, number, string[]][]
const PHRASE_CASES = phraseFixture.cases as [string, number, string[]][]

describe('wrapSubtitle: 文節で改行(バックエンドと同一ケース)', () => {
  it('ケース表を読めている', () => {
    expect(PHRASE_CASES.length).toBeGreaterThan(10)
  })

  it.each(PHRASE_CASES)('%s (max=%d)', (text, maxChars, expected) => {
    expect(wrapSubtitle(text, maxChars)).toEqual(expected)
  })

  it('文字を足しも削りもしない', () => {
    for (const [text, maxChars] of [...PHRASE_CASES, ...CHAR_CASES]) {
      expect(wrapSubtitle(text, maxChars).join('')).toBe(text)
    }
  })
})

describe('wrapChars: 文字数で折返し(バックエンドと同一ケース)', () => {
  it('ケース表を読めている', () => {
    expect(CHAR_CASES.length).toBeGreaterThan(20)
  })

  it.each(CHAR_CASES)('%s (max=%d)', (text, maxChars, expected) => {
    expect(wrapChars(text, maxChars)).toEqual(expected)
  })
})
