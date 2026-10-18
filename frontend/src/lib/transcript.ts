/**
 * 文字起こしの手直しまわりの純関数。
 *
 * 古い文字起こし(CLIの書き出し)は本文の先頭に「話者名: 」が付いている。
 * 画面では外して見せ、直した本文を保存するときに付け直す(付いていない行はそのまま)。
 */
import { ApiError, type Segment } from '../api/client'

const SPEAKER_PREFIX = /^[^:]+: /

export function splitSpeakerPrefix(text: string): { prefix: string; body: string } {
  const m = text.match(SPEAKER_PREFIX)
  return m ? { prefix: m[0], body: text.slice(m[0].length) } : { prefix: '', body: text }
}

/** 画面に出す本文(「話者名: 」を外したもの) */
export function displayText(text: string): string {
  return splitSpeakerPrefix(text).body
}

/** 直した本文を保存用の本文にする(元の行に付いていた「話者名: 」を付け直す) */
export function withSpeakerPrefix(original: string, body: string): string {
  return splitSpeakerPrefix(original).prefix + body
}

/** 動画に出てくる話者名(登場順・重複なし) */
export function speakersOf(segments: Pick<Segment, 'speaker'>[]): string[] {
  const seen: string[] = []
  for (const s of segments) {
    if (s.speaker && !seen.includes(s.speaker)) seen.push(s.speaker)
  }
  return seen
}

/** APIのエラーを画面に出す文にする(FastAPIの {"detail": "..."} を取り出す) */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    try {
      const parsed = JSON.parse(e.detail) as { detail?: unknown }
      if (typeof parsed.detail === 'string') return parsed.detail
    } catch {
      // JSONでなければ本文をそのまま出す
    }
    return e.detail
  }
  return e instanceof Error ? e.message : String(e)
}
