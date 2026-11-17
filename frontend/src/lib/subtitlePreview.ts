/**
 * プレビューの字幕(書き出しと同じ libass で描いた画像)を出すための純関数。
 *
 * 以前はここ(lib/subtitle.ts・lib/subtitleLayout.ts)で折り返しと位置をCSS向けに
 * 計算していた。規則を揃えても、CSSとlibassでは文字の大きさの意味・縁取り・
 * フォントの代替が違い、見た目は一致しなかった(issue #4)。いまは見た目を
 * 一切計算しない。バックエンドが返す時刻表のとおりに画像を出すだけ。
 */
import type { SubtitlePreviewEvent } from '../api/client'
import type { SettingsValues } from './settings'

export type SubtitlePosition = 'top' | 'center' | 'bottom'

export interface PreviewParams {
  /** クリップの字幕位置。無ければバックエンドが設定の値を使う(書き出しと同じ規則) */
  position?: SubtitlePosition | null
  offsetY?: number | null
  /** クリップの範囲(秒)。話者の色は書き出す範囲に出てくる話者で決まるため渡す */
  start?: number | null
  end?: number | null
}

/** APIに渡すクエリ文字列。無い値は付けない(0 は有効な値) */
export function previewQuery(p: PreviewParams): string {
  const q = new URLSearchParams()
  if (p.position) q.set('position', p.position)
  if (p.offsetY != null) q.set('offset_y', String(Math.round(p.offsetY)))
  if (p.start != null) q.set('start', String(p.start))
  if (p.end != null) q.set('end', String(p.end))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** 再生位置 t に出す字幕。時刻表は開始順(バックエンドが保証) */
export function activeEvent(
  events: SubtitlePreviewEvent[],
  t: number,
): SubtitlePreviewEvent | undefined {
  // 二分探索: 開始が t 以下の最後の1件
  let lo = 0
  let hi = events.length - 1
  let found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (events[mid].start <= t) {
      found = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  if (found < 0) return undefined
  const e = events[found]
  return t < e.end ? e : undefined
}

/**
 * 先に読み込んでおく画像のキー(今の字幕と、この後の count 件。重複なし)。
 * 字幕が切り替わる瞬間に描き始めると、再生中は出るのが遅れる。
 */
export function upcomingKeys(events: SubtitlePreviewEvent[], t: number, count = 4): string[] {
  const keys: string[] = []
  for (const e of events) {
    if (e.end <= t) continue
    if (!keys.includes(e.key)) keys.push(e.key)
    if (keys.length >= count) break
  }
  return keys
}

/**
 * 字幕の見た目に効く設定の指紋。変わったら時刻表を取り直す。
 * 見た目そのものはバックエンドが決めるので、ここは「変わったか」だけを見る。
 */
export function previewSignature(values: SettingsValues): string {
  const keys = Object.keys(values)
    .filter((k) => k.startsWith('subtitle_') || k === 'filler_level')
    .sort()
  return JSON.stringify(keys.map((k) => [k, values[k]]))
}
