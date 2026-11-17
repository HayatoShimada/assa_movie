/**
 * 動画プレビュー。再生位置をストアに流し、シーク関数を登録する。
 *
 * 字幕は書き出しと同じ libass で描いた透過画像を映像に重ねる
 * (backend/pipeline/subtitle_preview.py)。以前はCSSで描いていて、同じ設定でも
 * プレビューの文字が約1.45倍大きく、縁取りや表示時間も書き出しと違った(issue #4)。
 * 画面側は見た目を計算しない: 枠を書き出しと同じ縦横比にして、時刻表のとおりに
 * 画像を枠いっぱいに重ねるだけ。
 *
 * 再生操作はブラウザ標準のコントロール(動画の上に重なる)を使わず、映像の枠の
 * 下に置く。標準のコントロールは映像の下端に重なり、下配置の字幕が隠れて
 * 読めなかった。
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { API_BASE, api, type Orientation } from '../../api/client'
import type { ConvertMethod } from '../../lib/catalogs'
import {
  activeEvent,
  previewQuery,
  previewSignature,
  upcomingKeys,
  type SubtitlePosition,
} from '../../lib/subtitlePreview'
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
  segmentsVersion = 0,
  styleValues,
  subtitlePosition = null,
  subtitleOffsetY = null,
  clipStart = null,
  clipEnd = null,
  outputOrientation = 'landscape',
  convertMethod = null,
  cropX = 0.5,
}: {
  mediaId: number
  /** 文字起こしが変わったら変わる値(字幕の時刻表を取り直す合図) */
  segmentsVersion?: number
  /** プロジェクト設定を反映済みの設定値(lib/settings.ts の resolveSettings) */
  styleValues: SettingsValues
  /** クリップの字幕位置。null なら設定の値(書き出しと同じ規則をバックエンドが適用) */
  subtitlePosition?: SubtitlePosition | null
  subtitleOffsetY?: number | null
  /** クリップの範囲。話者の色は書き出す範囲で決まるので、クリップを見ているときは渡す */
  clipStart?: number | null
  clipEnd?: number | null
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

  // 字幕の時刻表。見た目に効くもの(設定・文字起こし・クリップの位置と範囲)が
  // 変わったら取り直す。取り直す間は前の字幕を出し続ける(ちらつかせない)
  const query = previewQuery({
    position: subtitlePosition,
    offsetY: subtitleOffsetY,
    start: clipStart,
    end: clipEnd,
  })
  const preview = useQuery({
    queryKey: [
      'subtitle-preview',
      mediaId,
      query,
      outputOrientation,
      previewSignature(styleValues),
      segmentsVersion,
    ],
    queryFn: () => api.getSubtitlePreview(mediaId, query),
    placeholderData: keepPreviousData,
  })
  const events = preview.data?.events ?? []
  const available = preview.data?.available ?? true
  const active = activeEvent(events, currentTime)
  const imageUrl = (key: string) => api.subtitlePreviewImageUrl(mediaId, key, query)

  // この後の字幕を先に読み込む(切り替わる瞬間に描き始めると再生中に遅れる)
  const upcoming = available ? upcomingKeys(events, currentTime).join(',') : ''
  useEffect(() => {
    if (!upcoming) return
    for (const key of upcoming.split(',')) {
      new Image().src = api.subtitlePreviewImageUrl(mediaId, key, query)
    }
  }, [upcoming, mediaId, query])

  // 描けなかった字幕(ffmpegが無い・失敗)。黙って字幕なしに見せない
  const [failedKey, setFailedKey] = useState<string | null>(null)
  const failed = active != null && failedKey === active.key

  const isPortrait = outputOrientation === 'portrait'
  // 枠は書き出される動画と同じ縦横比にする(字幕の画像は枠いっぱいに重ねる)
  const aspect = preview.data
    ? `${preview.data.width} / ${preview.data.height}`
    : isPortrait
      ? '9 / 16'
      : '16 / 9'
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
          isPortrait ? 'max-h-[80vh]' : 'w-full'
        }`}
        style={{ aspectRatio: aspect }}
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
        {active && available && !failed && (
          // 書き出しの解像度で描いた透過画像。枠と同じ縦横比なので、枠いっぱいに
          // 伸ばせば位置も大きさも書き出しと同じ比率になる
          <img
            key={active.key}
            data-testid="subtitle-overlay"
            data-key={active.key}
            className="pointer-events-none absolute inset-0 h-full w-full select-none"
            src={imageUrl(active.key)}
            alt={active.text}
            draggable={false}
            onError={() => setFailedKey(active.key)}
          />
        )}
      </div>
      {(!available || failed) && (
        <p data-testid="subtitle-preview-unavailable" className="mt-1 text-xs text-amber-700 dark:text-amber-400">
          字幕のプレビューを表示できません
          {preview.data?.reason ? `(${preview.data.reason})` : '(字幕を描く処理に失敗しました)'}
          。書き出しには影響しません。
          {active && <span className="ml-1 text-neutral-500">いまの字幕: {active.text}</span>}
        </p>
      )}
      <PlayerControls video={videoEl} currentTime={currentTime} />
    </div>
  )
}
