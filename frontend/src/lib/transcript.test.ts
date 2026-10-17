import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import {
  displayText,
  errorText,
  speakersOf,
  splitSpeakerPrefix,
  withSpeakerPrefix,
} from './transcript'

describe('話者名の前置き', () => {
  it.each([
    ['はやまる: それがすごく良くて', 'はやまる: ', 'それがすごく良くて'],
    ['それがすごく良くて', '', 'それがすごく良くて'],
    // 本文中の「:」は前置きではない(先頭の「名前: 」だけを外す)
    ['時刻は10:30です', '', '時刻は10:30です'],
  ])('%s', (text, prefix, body) => {
    expect(splitSpeakerPrefix(text)).toEqual({ prefix, body })
    expect(displayText(text)).toBe(body)
  })

  it('直した本文に、元の行の前置きを付け直す', () => {
    expect(withSpeakerPrefix('はやまる: 腕駒の話', '腕前の話')).toBe('はやまる: 腕前の話')
    expect(withSpeakerPrefix('腕駒の話', '腕前の話')).toBe('腕前の話')
  })
})

describe('speakersOf', () => {
  it('登場順で重複なし。話者なしの行は数えない', () => {
    expect(
      speakersOf([
        { speaker: '話者B' },
        { speaker: null },
        { speaker: '話者A' },
        { speaker: '話者B' },
      ]),
    ).toEqual(['話者B', '話者A'])
  })
})

describe('errorText', () => {
  it('FastAPIのdetailを取り出す', () => {
    expect(errorText(new ApiError(400, '{"detail":"名前を入れてください"}'))).toBe(
      '名前を入れてください',
    )
  })
  it('JSONでなければ本文をそのまま', () => {
    expect(errorText(new ApiError(500, 'Internal Server Error'))).toBe('Internal Server Error')
    expect(errorText(new Error('通信できません'))).toBe('通信できません')
  })
})
