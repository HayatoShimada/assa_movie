import { describe, expect, it } from 'vitest'
import { answeredMessage, formatTermList, parseTermList } from './userTerms'

describe('parseTermList(聞き間違いの入力欄)', () => {
  it.each([
    // [入力, 期待]
    ['反動体', ['反動体']],
    // 日本語の読点・カンマ・改行のどれで区切ってもよい
    ['反動体、はんどう体', ['反動体', 'はんどう体']],
    ['反動体,はんどう体，半道体', ['反動体', 'はんどう体', '半道体']],
    ['反動体\nはんどう体', ['反動体', 'はんどう体']],
    // 空・空白だけ・重複は除く
    ['', []],
    ['  、 ,', []],
    ['反動体、 反動体 ', ['反動体']],
  ])('%j → %j', (input, expected) => {
    expect(parseTermList(input)).toEqual(expected)
  })

  it('表示用の形に戻すと読点でつながる', () => {
    expect(formatTermList(['反動体', 'はんどう体'])).toBe('反動体、はんどう体')
    expect(parseTermList(formatTermList(['反動体', 'はんどう体']))).toEqual([
      '反動体',
      'はんどう体',
    ])
  })
})

describe('answeredMessage(質問に答えたときの案内)', () => {
  it.each([
    // [質問の種類, 修正した箇所数, 回答, 案内]
    [
      'term',
      3,
      '半導体',
      '3箇所を修正し、「半導体」を辞書に覚えました(次の文字起こしから使います)',
    ],
    // 表記がそのままで正しいと答えたとき(直す箇所は無いが辞書には覚える)
    ['term', 0, '箱ストア', '「箱ストア」を辞書に覚えました(次の文字起こしから使います)'],
    // フィラーの質問は辞書に入らない
    ['filler', 2, '削除', '2箇所を修正しました'],
  ])('%s・%d箇所・%s', (kind, changed, answer, expected) => {
    expect(answeredMessage(kind, changed, answer)).toBe(expected)
  })
})
