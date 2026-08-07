/**
 * 動画プレビュー。再生位置をストアに流し、シーク関数を登録する。
 *
 * 字幕の位置・サイズはバックエンド(pipeline/subtitle.py scaled_style)と
 * 同じ相対規則で描く。規則そのものは lib/subtitleLayout.ts の純関数にあり、
 * テストで期待値を固定している。
 */
import { useEffect, useRef } from 'react'
import { API_BASE, type Orientation, type Segment } from '../../api/client'
import type { ConvertMethod } from '../../lib/catalogs'
import { wrapSubtitle } from '../../lib/subtitle'
import { hexToRgba, overlayGeometry, type SubtitlePosition } from '../../lib/subtitleLayout'
import type { SettingsValues } from '../../lib/settings'
import { usePlayback } from '../../stores/playback'

export function VideoPlayer({
  mediaId,
  segments,
  styleValues,
  subtitlePosition = 'bottom',
  subtitleOffsetY = 0,
  outputOrientation = 'landscape',
  convertMethod = null,
  cropX = 0.5,
}: {
  mediaId: number
  segments: Segment[]
  /** プロジェクト設定を反映済みの設定値(lib/settings.ts の resolveSettings) */
  styleValues: SettingsValues
  subtitlePosition?: SubtitlePosition
  subtitleOffsetY?: number
  outputOrientation?: Orientation
  /** 縦横変換のプレビュー。cropのみ実映像で近似できる */
  convertMethod?: ConvertMethod | null
  cropX?: number
}) {
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

  const v = styleValues
  const maxChars = Number(v.subtitle_max_chars_per_line ?? 15)
  const fontSize = Number(v.subtitle_font_size ?? 48)
  const fontFamily = String(v.subtitle_font_family ?? 'Noto Sans JP')
  const textColor = String(v.subtitle_text_color ?? '#FFFFFF')
  const bg = String(v.subtitle_bg ?? 'none')
  const bgColor = String(v.subtitle_bg_color ?? '#000000')
  const bgOpacity = Number(v.subtitle_bg_opacity ?? 0.5)

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
  const { fontSize: fontSizeCq, ...overlayStyle } = overlayGeometry(
    subtitlePosition,
    subtitleOffsetY,
    fontSize,
  )

  const isPortrait = outputOrientation === 'portrait'
  // crop: 実映像で切り出し位置を再現。blur_pad/face: 全体表示(書き出し時に背景合成)
  const videoFit =
    convertMethod === 'crop'
      ? ({ objectFit: 'cover', objectPosition: `${cropX * 100}% 50%` } as const)
      : isPortrait || convertMethod
        ? ({ objectFit: 'contain' } as const)
        : undefined

  return (
    <div
      data-testid="player-frame"
      data-orientation={outputOrientation}
      className={`relative mx-auto overflow-hidden rounded-lg bg-black ${
        isPortrait ? 'aspect-[9/16] max-h-[80vh]' : 'aspect-video w-full'
      }`}
      style={{ containerType: 'inline-size' }}
    >
      <video
        ref={ref}
        data-testid="video"
        className="h-full w-full"
        style={videoFit}
        src={`${API_BASE}/api/media/${mediaId}/file`}
        controls
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
      />
      {convertMethod && convertMethod !== 'crop' && isPortrait && (
        <p className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
          {convertMethod === 'blur_pad' ? '書き出し時: 余白はぼかし背景' : '書き出し時: 顔検出で自動レイアウト'}
        </p>
      )}
      {lines.length > 0 && (
        <p
          data-testid="subtitle-overlay"
          className="pointer-events-none absolute text-center font-bold"
          style={{
            ...overlayStyle,
            fontSize: fontSizeCq,
            fontFamily: `'${fontFamily}', sans-serif`,
            color: textColor,
            lineHeight: 1.2,
            textShadow: bg === 'box' ? 'none' : '0 0 4px rgba(0,0,0,.9), 0 0 8px rgba(0,0,0,.7)',
          }}
        >
          {lines.map((line, i) => (
            <span
              key={i}
              className="mx-auto block w-fit"
              style={
                bg === 'box'
                  ? { backgroundColor: hexToRgba(bgColor, bgOpacity), padding: '0 0.3em' }
                  : undefined
              }
            >
              {line}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
