/**
 * 字幕折返し・禁則処理(backend/pipeline/subtitle.py のTS移植)。
 * プレビュー(CSSオーバーレイ)と書き出し(ASS焼き込み)の見た目を揃えるため、
 * バックエンドと同一のテストケースを通すこと。
 */

const KINSOKU_HEAD = new Set(
  '、。,,..!!??)〕]}」』〉》ー・:;゛゜ゝゞ々ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ…‥',
)
const KINSOKU_TAIL = new Set('「『((〔[{〈《')
const HANG_ALLOWANCE = 2

export function wrapSubtitle(text: string, maxChars = 15): string[] {
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
