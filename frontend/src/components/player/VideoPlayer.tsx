/**
 * 動画プレビュー。再生位置をストアに流し、シーク関数を登録する。
 *
 * 字幕の位置・サイズはバックエンド(pipeline/subtitle.py scaled_style)と
 * 同じ相対規則で描く。規則そのものは lib/subtitleLayout.ts の純関数にあり、
 * テストで期待値を固定している。
 *
 * 再生操作はブラウザ標準のコントロール(動画の上に重なる)を使わず、映像の枠の
 * 下に置く。標準のコントロールは映像の下端に重なり、下配置の字幕が隠れて
 * 読めなかった。枠(cqw/cqhの基準)は映像そのものなので、書き出しとの対応は変わらない。
 */
import { useEffect, useRef, useState } from 'react'
import { API_BASE, type Orientation, type Segment } from '../../api/client'
import type { ConvertMethod } from '../../lib/catalogs'
import { wrapSubtitle } from '../../lib/subtitle'
import { hexToRgba, overlayGeometry, type SubtitlePosition } from '../../lib/subtitleLayout'
import type { SettingsValues } from '../../lib/settings'
import { usePlayback } from '../../stores/playback'
import { formatTime } from '../ui'

/** 映像の下に置く再生操作(再生/一時停止・シーク・時刻・ミュート) */
function PlayerControls({
  video,
  currentTime,
}: {
  video: HTMLVideoElement | null
  currentTime: number
}) {
  const [playing, setPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [muted, setMuted] = useState(false)

  useEffect(() => {
    if (!video) return
    const sync = () => {
      setPlaying(!video.paused && !video.ended)
      setDuration(Number.isFinite(video.duration) ? video.duration : 0)
      setMuted(video.muted)
    }
    const events = ['play', 'pause', 'ended', 'loadedmetadata', 'durationchange', 'volumechange']
    events.forEach((e) => video.addEventListener(e, sync))
    sync()
    return () => events.forEach((e) => video.removeEventListener(e, sync))
  }, [video])

  const btn =
    'flex h-8 w-8 shrink-0 items-center justify-center rounded hover:bg-neutral-200 disabled:opacity-40 dark:hover:bg-neutral-800'
  return (
    <div data-testid="player-controls" className="mt-2 flex items-center gap-2 text-xs">
      <button
        type="button"
        data-testid="player-play"
        className={btn}
        disabled={!video}
        aria-label={playing ? '一時停止' : '再生'}
        title={playing ? '一時停止' : '再生'}
        onClick={() => (playing ? video?.pause() : void video?.play().catch(() => {}))}
      >
        {playing ? (
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            className="fill-current"
            aria-hidden="true"
          >
            <rect x="2" y="1" width="3.5" height="12" rx="1" />
            <rect x="8.5" y="1" width="3.5" height="12" rx="1" />
          </svg>
        ) : (
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            className="fill-current"
            aria-hidden="true"
          >
            <path d="M3 1.5v11l9.5-5.5z" />
          </svg>
        )}
      </button>
      <input
        data-testid="player-seek"
        type="range"
        aria-label="再生位置"
        className="min-w-0 flex-1"
        min={0}
        max={duration || 0}
        step={0.1}
        value={Math.min(currentTime, duration || currentTime)}
        disabled={!video || !duration}
        onChange={(e) => {
          if (video) video.currentTime = Number(e.target.value)
        }}
      />
      <span data-testid="player-time" className="shrink-0 font-mono tabular-nums text-neutral-500">
        {formatTime(currentTime)} / {formatTime(duration)}
      </span>
      <button
        type="button"
        data-testid="player-mute"
        className={btn}
        disabled={!video}
        aria-label={muted ? '音を出す' : '音を消す'}
        title={muted ? '音を出す' : '音を消す'}
        onClick={() => {
          if (video) video.muted = !video.muted
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          className="stroke-current"
          fill="none"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <path d="M2 6h3l4-3v10l-4-3H2z" className="fill-current" />
          {muted ? <path d="M11 6l4 4m0-4l-4 4" /> : <path d="M11.5 5.5a3.5 3.5 0 0 1 0 5" />}
        </svg>
      </button>
    </div>
  )
}

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
  // 再生操作に要素を渡すため、マウント後に再レンダリングさせる
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null)
  const setCurrentTime = usePlayback((s) => s.setCurrentTime)
  const setSeeker = usePlayback((s) => s.setSeeker)
  const currentTime = usePlayback((s) => s.currentTime)

  useEffect(() => {
    const video = ref.current
    if (!video) return
    setSeeker((t) => {
      video.currentTime = t
    })
    setVideoEl(video)
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
    <div>
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
          // 映像のクリックでも再生/一時停止できるようにする(標準コントロールの代わり)
          onClick={(e) => {
            const v = e.currentTarget
            if (v.paused) void v.play().catch(() => {})
            else v.pause()
          }}
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        />
        {convertMethod && convertMethod !== 'crop' && isPortrait && (
          <p className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
            {convertMethod === 'blur_pad'
              ? '書き出し時: 余白はぼかし背景'
              : '書き出し時: 顔検出で自動レイアウト'}
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
      <PlayerControls video={videoEl} currentTime={currentTime} />
    </div>
  )
}
