/**
 * 利用者の辞書(名前・用語)の表示まわりの純関数。
 * 辞書そのものはバックエンド(backend/core/user_terms.py)が持つ。
 */

/** 聞き間違いの入力欄の文字列を一覧にする(読点・カンマ・改行で区切る) */
export function parseTermList(text: string): string[] {
  const out: string[] = []
  for (const raw of text.split(/[、,，\n]/)) {
    const item = raw.trim()
    if (item && !out.includes(item)) out.push(item)
  }
  return out
}

/** 一覧を入力欄に入れる形にする(parseTermList の逆) */
export function formatTermList(items: string[]): string {
  return items.join('、')
}

/**
 * 質問に答えたあとに出す案内。
 * 固有名詞の質問は辞書に覚えるので、そのことと、いつ効くかを伝える。
 * フィラーの質問は辞書に入らないので修正件数だけ伝える。
 */
export function answeredMessage(kind: string, segmentsChanged: number, answer: string): string {
  if (kind !== 'term') return `${segmentsChanged}箇所を修正しました`
  const fixed = segmentsChanged > 0 ? `${segmentsChanged}箇所を修正し、` : ''
  return `${fixed}「${answer}」を辞書に覚えました(次の文字起こしから使います)`
}
