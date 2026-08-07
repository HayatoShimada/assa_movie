/**
 * 動画プレビュー。再生位置をストアに流し、シーク関数を登録する。
 * 字幕オーバーレイは現在セグメントのテキストをCSSで重ねる(スタイル調整はM7)。
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { API_BASE, api, type Segment } from '../../api/client'
import { wrapSubtitle } from '../../lib/subtitle'
import { usePlayback } from '../../stores/playback'

export function VideoPlayer({ mediaId, segments }: { mediaId: number; segments: Segment[] }) {
  const ref = useRef<HTMLVideoElement>(null)
  const setCurrentTime = usePlayback((s) => s.setCurrentTime)
  const setSeeker = usePlayback((s) => s.setSeeker)
  const currentTime = usePlayback((s) => s.currentTime)

  useEffect(() => {
    const video = ref.current
    if (!video) return
    setSeeker((t) => {
      video.currentTime = t
    })
    return () => setSeeker(null)
  }, [setSeeker])

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const maxChars = Number(settings.data?.values.subtitle_max_chars_per_line ?? 15)

  // 採用ジャッジ(選択字幕)と相槌を反映して現在の字幕を選ぶ
  const active = segments.find(
    (s) =>
      !s.is_aizuchi &&
      (s.subtitle_show === 'auto_show' || s.subtitle_show === 'user_show') &&
      s.start <= currentTime &&
      currentTime < s.end,
  )
  // 話者ラベル(「はやまる: 」)を外し、書き出しと同じ折返し・禁則を適用する
  const lines = active ? wrapSubtitle(active.text.replace(/^[^:]+: /, ''), maxChars) : []

  return (
    <div className="relative overflow-hidden rounded-lg bg-black">
      <video
        ref={ref}
        data-testid="video"
        className="aspect-video w-full"
        src={`${API_BASE}/api/media/${mediaId}/file`}
        controls
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
      />
      {lines.length > 0 && (
        <p
          data-testid="subtitle-overlay"
          className="pointer-events-none absolute inset-x-4 bottom-14 text-center text-lg font-bold text-white"
          style={{ textShadow: '0 0 4px rgba(0,0,0,.9), 0 0 8px rgba(0,0,0,.7)' }}
        >
          {lines.map((line, i) => (
            <span key={i} className="block">
              {line}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
