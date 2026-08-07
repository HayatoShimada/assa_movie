/**
 * 動画プレビュー。再生位置をストアに流し、シーク関数を登録する。
 * 字幕オーバーレイは現在セグメントのテキストをCSSで重ねる(スタイル調整はM7)。
 */
import { useEffect, useRef } from 'react'
import { API_BASE, type Segment } from '../../api/client'
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

  const active = segments.find(
    (s) => !s.is_aizuchi && s.start <= currentTime && currentTime < s.end,
  )
  // 字幕は話者ラベル(「はやまる: 」)を外して表示する
  const subtitle = active?.text.replace(/^[^:]+: /, '')

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
      {subtitle && (
        <p
          data-testid="subtitle-overlay"
          className="pointer-events-none absolute inset-x-4 bottom-14 text-center text-lg font-bold text-white"
          style={{ textShadow: '0 0 4px rgba(0,0,0,.9), 0 0 8px rgba(0,0,0,.7)' }}
        >
          {subtitle}
        </p>
      )}
    </div>
  )
}
