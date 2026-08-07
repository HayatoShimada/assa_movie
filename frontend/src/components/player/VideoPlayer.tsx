/**
 * 動画プレビュー。再生位置をストアに流し、シーク関数を登録する。
 *
 * 字幕オーバーレイはバックエンド(pipeline/subtitle.py scaled_style)と同じ
 * 相対規則で描く: フォント・左右余白は「画面幅に対する比率」、上下余白は
 * 「画面高さに対する比率」。コンテナクエリ単位(cqw/cqh)で実現し、
 * どの出力向き・ウィンドウ幅でも書き出しと同じ見た目比率になる。
 *   フォント: font_size(1920幅基準px) / 1920 → cqw
 *   上下余白: (40±offset)(1080高基準px) / 1080 → cqh
 */
import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { API_BASE, api, type Orientation, type Segment } from '../../api/client'
import { wrapSubtitle } from '../../lib/subtitle'
import { usePlayback } from '../../stores/playback'

type SubtitlePosition = 'top' | 'center' | 'bottom'
type ConvertMethod = 'crop' | 'blur_pad' | 'face' | null

/** バックエンドの hex + 不透明度 → CSS rgba */
function hexToRgba(hex: string, opacity: number): string {
  const h = hex.replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return `rgba(0,0,0,${opacity})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${opacity})`
}

export function VideoPlayer({
  mediaId,
  segments,
  subtitlePosition = 'bottom',
  subtitleOffsetY = 0,
  outputOrientation = 'landscape',
  convertMethod = null,
  cropX = 0.5,
  styleValues,
}: {
  mediaId: number
  segments: Segment[]
  subtitlePosition?: SubtitlePosition
  subtitleOffsetY?: number
  outputOrientation?: Orientation
  /** 縦横変換のプレビュー(クリップ選択時)。cropのみ実映像で近似できる */
  convertMethod?: ConvertMethod
  cropX?: number
  /** プロジェクト設定を反映した設定値(省略時はグローバル設定) */
  styleValues?: Record<string, unknown>
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

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const v = styleValues ?? settings.data?.values ?? {}
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

  // 上下余白は高さ基準(バックエンドの margin_v=40±offset @1080 と同じ比率)
  const offset = Math.max(-120, Math.min(120, subtitleOffsetY))
  const cqh = (px: number) => `${((Math.max(0, px) / 1080) * 100).toFixed(3)}cqh`
  const overlayStyle =
    subtitlePosition === 'top'
      ? { top: cqh(40 + offset) }
      : subtitlePosition === 'center'
        ? { top: '50%', transform: 'translateY(-50%)' }
        : { bottom: cqh(40 - offset) }

  const isPortrait = outputOrientation === 'portrait'
  // crop: 実映像で切り出し位置を再現。blur_pad/face: 全体表示(書き出し時に背景合成)
  const videoFit =
    isPortrait || convertMethod
      ? convertMethod === 'crop'
        ? ({ objectFit: 'cover', objectPosition: `${(cropX ?? 0.5) * 100}% 50%` } as const)
        : ({ objectFit: 'contain' } as const)
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
            left: `${((60 / 1920) * 100).toFixed(3)}cqw`,
            right: `${((60 / 1920) * 100).toFixed(3)}cqw`,
            fontSize: `${((fontSize / 1920) * 100).toFixed(3)}cqw`,
            fontFamily: `'${fontFamily}', sans-serif`,
            color: textColor,
            lineHeight: 1.2,
            textShadow:
              bg === 'box' ? 'none' : '0 0 4px rgba(0,0,0,.9), 0 0 8px rgba(0,0,0,.7)',
          }}
        >
          {lines.map((line, i) => (
            <span
              key={i}
              className="block w-fit mx-auto"
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
