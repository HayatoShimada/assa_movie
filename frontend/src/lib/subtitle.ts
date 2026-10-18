/**
 * 字幕折返し・禁則処理(backend/pipeline/subtitle.py のTS移植)。
 * プレビュー(CSSオーバーレイ)と書き出し(ASS焼き込み)の見た目を揃えるため、
 * バックエンドと同一のテストケースを通すこと。
 * 文節の区切りはBudouX(pyproject.toml の budoux と同じバージョン)で決める。
 */
// loadDefaultJapaneseParser はHTML処理つきのParserを返し、linkedom等まで
// バンドルに入る(+213KB)。文節に区切るだけなのでParserとモデルだけ使う
import { Parser, jaModel } from 'budoux'

const KINSOKU_HEAD = new Set(
  '、。,,..!!??)〕]}」』〉》ー・:;゛゜ゝゞ々ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ…‥',
)
const KINSOKU_TAIL = new Set('「『((〔[{〈《')
const HANG_ALLOWANCE = 2
// 中身を1つのまとまりとして扱う括弧(カッコ注釈の途中で改行しない)。「」は対象外
const GROUP_OPEN = new Set('((')
const GROUP_CLOSE = new Set('))')

let parser: Parser | null = null

/** 文字数(コードポイント単位。Pythonのlenと揃える) */
const len = (s: string) => [...s].length
const first = (s: string) => [...s][0]
const last = (s: string) => [...s].at(-1) ?? ''

/** BudouXの文節を、改行してよい単位にまとめ直す */
function phrases(text: string): string[] {
  parser ??= new Parser(jaModel)
  const out: string[] = []
  let depth = 0
  for (const phrase of parser.parse(text)) {
    if (
      out.length &&
      (KINSOKU_HEAD.has(first(phrase)) || KINSOKU_TAIL.has(last(out[out.length - 1])) || depth > 0)
    ) {
      out[out.length - 1] += phrase
    } else {
      out.push(phrase)
    }
    for (const ch of phrase) {
      if (GROUP_OPEN.has(ch)) depth += 1
      else if (GROUP_CLOSE.has(ch) && depth) depth -= 1
    }
  }
  return out
}

/**
 * 字幕折返し。文節の切れ目で改行する。
 * 1つの文節が1行に収まらないときだけ wrapChars(文字数で折返し)に任せる。
 */
export function wrapSubtitle(text: string, maxChars = 15): string[] {
  if (maxChars < 2) maxChars = 2
  if (len(text) <= maxChars) return [text]
  const lines: string[] = []
  let cur = ''
  for (const phrase of phrases(text)) {
    let body = [...phrase]
    while (body.length && KINSOKU_HEAD.has(body[body.length - 1])) body = body.slice(0, -1)
    const hangs =
      cur !== '' &&
      len(cur) + body.length <= maxChars &&
      len(cur) + len(phrase) <= maxChars + HANG_ALLOWANCE
    if (len(cur) + len(phrase) <= maxChars || hangs) {
      cur += phrase
    } else if (len(phrase) <= maxChars) {
      lines.push(cur)
      cur = phrase
    } else {
      const parts = wrapChars(cur + phrase, maxChars)
      lines.push(...parts.slice(0, -1))
      cur = parts[parts.length - 1]
    }
  }
  lines.push(cur)
  const kept = lines.filter((l) => l)
  return kept.length ? kept : ['']
}

/** 文字数での字幕折返し(文節が1行に収まらないときの受け皿) */
export function wrapChars(text: string, maxChars = 15): string[] {
  if (maxChars < 2) maxChars = 2
  const chars = [...text]
  const lines: string[] = []
  let i = 0
  const n = chars.length
  while (i < n) {
    let end = Math.min(i + maxChars, n)
    // ぶら下げ: 次の文字が行頭禁則なら行末に含める(上限あり)
    while (end < n && KINSOKU_HEAD.has(chars[end]) && end - i < maxChars + HANG_ALLOWANCE) {
      end += 1
    }
    // ぶら下げ上限でも次行頭が禁則のままなら、安全な切れ目まで戻す(追い出し)
    if (end < n && KINSOKU_HEAD.has(chars[end])) {
      let back = end
      while (back > i + 1 && KINSOKU_HEAD.has(chars[back])) back -= 1
      if (!KINSOKU_HEAD.has(chars[back])) end = back
    }
    // 行末禁則: 開き括弧は次の行へ送る
    while (end > i + 1 && KINSOKU_TAIL.has(chars[end - 1])) end -= 1
    lines.push(chars.slice(i, end).join(''))
    i = end
  }
  return lines.length ? lines : ['']
}
