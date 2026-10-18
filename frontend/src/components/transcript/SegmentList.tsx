/**
 * セグメント一覧(仮想スクロール)。
 * クリックで動画シーク、再生位置に追従してハイライト、相槌はグレー表示。
 *
 * 手直しもここで行う:
 *   - 本文: 行のダブルクリックか鉛筆ボタンで編集欄を出す(原文は常に残り、いつでも戻せる)
 *   - 話者: 話者名を押すと、名前の変更(この動画の全行)と、この行だけの付け替えができる
 * 保存はコールバックに任せる(APIとの繋ぎは TranscriptPanel)。
 */
import { useVirtualizer } from '@tanstack/react-virtual'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Segment } from '../../api/client'
import { displayText, errorText, speakersOf, withSpeakerPrefix } from '../../lib/transcript'
import { usePlayback } from '../../stores/playback'
import { Button, formatTime, speakerColor } from '../ui'

export interface SegmentEditHandlers {
  onSaveText?: (seg: Segment, text: string) => Promise<unknown>
  onRestore?: (seg: Segment) => Promise<unknown>
  onSetSpeaker?: (seg: Segment, speaker: string) => Promise<unknown>
  onRenameSpeaker?: (current: string, next: string) => Promise<unknown>
}

function PencilIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" />
      <path d="M13.5 6.5l4 4" />
    </svg>
  )
}

/** 行の中の操作欄。クリックが行(選択+シーク)に伝わらないようにする */
function Panel({ children, testId }: { children: ReactNode; testId: string }) {
  return (
    <div
      data-testid={testId}
      className="mx-3 mb-2 cursor-auto space-y-2 rounded-md border border-neutral-200 bg-white p-2 text-sm dark:border-neutral-700 dark:bg-neutral-950"
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>
  )
}

function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (fn: () => Promise<unknown>, onDone?: () => void) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onDone?.()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

function TextEditor({
  seg,
  handlers,
  onClose,
}: {
  seg: Segment
  handlers: SegmentEditHandlers
  onClose: () => void
}) {
  const [value, setValue] = useState(displayText(seg.text))
  const action = useAction()
  const changed = value !== displayText(seg.text)
  const save = () => {
    if (!changed) return onClose()
    if (!value.trim() || !handlers.onSaveText) return
    action.run(() => handlers.onSaveText!(seg, withSpeakerPrefix(seg.text, value)), onClose)
  }

  return (
    <Panel testId={`segment-editor-${seg.idx}`}>
      <textarea
        data-testid={`segment-edit-input-${seg.idx}`}
        aria-label="この行の文字"
        autoFocus
        rows={2}
        className="w-full resize-y rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          // 日本語入力の変換確定のEnterでは保存しない
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            save()
          }
          if (e.key === 'Escape') onClose()
        }}
      />
      {seg.text !== seg.original_text && (
        <p className="text-xs text-neutral-500">原文: {displayText(seg.original_text)}</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          data-testid={`segment-edit-save-${seg.idx}`}
          className="!px-2 !py-0.5 text-xs"
          disabled={action.busy || !value.trim()}
          onClick={save}
        >
          保存
        </Button>
        <Button variant="ghost" className="!px-2 !py-0.5 text-xs" onClick={onClose}>
          やめる
        </Button>
        {/* 手で直した行だけ。AIの修正(レビュータブで承認したもの)は残る */}
        {seg.edited_by_user && handlers.onRestore && (
          <Button
            data-testid={`segment-restore-${seg.idx}`}
            variant="ghost"
            className="!px-2 !py-0.5 text-xs"
            title="手で直す前の文に戻します。レビューで承認したAIの修正は残ります"
            disabled={action.busy}
            onClick={() => action.run(() => handlers.onRestore!(seg), onClose)}
          >
            手直しを取り消す
          </Button>
        )}
        <span className="ml-auto text-xs text-neutral-400">Enterで保存 / Escでやめる</span>
      </div>
      {!value.trim() && <p className="text-xs text-red-600">空にはできません</p>}
      {action.error && <p className="text-xs text-red-600">{action.error}</p>}
    </Panel>
  )
}

function SpeakerMenu({
  seg,
  speakers,
  handlers,
  onClose,
}: {
  seg: Segment
  speakers: string[]
  handlers: SegmentEditHandlers
  onClose: () => void
}) {
  const current = seg.speaker ?? ''
  const [name, setName] = useState(current)
  const action = useAction()
  const others = speakers.filter((s) => s !== current)

  return (
    <Panel testId={`speaker-menu-${seg.idx}`}>
      <form
        className="space-y-1"
        onSubmit={(e) => {
          e.preventDefault()
          if (!handlers.onRenameSpeaker || name.trim() === current) return
          action.run(() => handlers.onRenameSpeaker!(current, name), onClose)
        }}
      >
        <label className="block text-xs text-neutral-500" htmlFor={`speaker-rename-${seg.id}`}>
          「{current}」の名前を変える(この動画の「{current}」の行がすべて変わります)
        </label>
        <div className="flex gap-2">
          <input
            id={`speaker-rename-${seg.id}`}
            data-testid={`speaker-rename-input-${seg.idx}`}
            autoFocus
            className="min-w-0 flex-1 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
          />
          <Button
            type="submit"
            data-testid={`speaker-rename-save-${seg.idx}`}
            className="!px-2 !py-0.5 text-xs"
            disabled={action.busy || !name.trim() || name.trim() === current}
          >
            名前を変える
          </Button>
        </div>
      </form>
      {others.length > 0 && handlers.onSetSpeaker && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-neutral-500">この行だけ別の話者にする:</span>
          {others.map((o) => (
            <button
              key={o}
              type="button"
              data-testid={`speaker-assign-${seg.idx}-${o}`}
              disabled={action.busy}
              className={`rounded px-1.5 py-0.5 text-xs font-medium ${speakerColor(o)}`}
              onClick={() => action.run(() => handlers.onSetSpeaker!(seg, o), onClose)}
            >
              {o}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button variant="ghost" className="!px-2 !py-0.5 text-xs" onClick={onClose}>
          閉じる
        </Button>
        {action.error && <p className="text-xs text-red-600">{action.error}</p>}
      </div>
    </Panel>
  )
}

export function SegmentList({
  segments,
  ...handlers
}: { segments: Segment[] } & SegmentEditHandlers) {
  const parentRef = useRef<HTMLDivElement>(null)
  const currentTime = usePlayback((s) => s.currentTime)
  const seekTo = usePlayback((s) => s.seekTo)
  const selectedId = usePlayback((s) => s.selectedSegmentId)
  const selectSegment = usePlayback((s) => s.selectSegment)
  // 手直し中の行と、話者メニューを開いている行(同時に開くのはどちらか1つ)
  const [open, setOpen] = useState<{ id: number; kind: 'text' | 'speaker' } | null>(null)
  // ユーザーがリストを触っている間は自動追従スクロールを止める
  const userScrolling = useRef(false)
  const scrollTimer = useRef<number>(0)
  const speakers = speakersOf(segments)
  const canEditText = Boolean(handlers.onSaveText)

  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 56,
    overscan: 10,
  })

  const activeIndex = segments.findIndex((s) => s.start <= currentTime && currentTime < s.end)

  useEffect(() => {
    // 手直し中に再生位置が進んでも、編集中の行から勝手に離れない
    if (activeIndex >= 0 && !userScrolling.current && open === null) {
      virtualizer.scrollToIndex(activeIndex, { align: 'center' })
    }
  }, [activeIndex, virtualizer, open])

  return (
    <div
      ref={parentRef}
      data-testid="segment-list"
      className="h-full overflow-y-auto"
      onWheel={() => {
        userScrolling.current = true
        window.clearTimeout(scrollTimer.current)
        scrollTimer.current = window.setTimeout(() => (userScrolling.current = false), 3000)
      }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((row) => {
          const seg = segments[row.index]
          const isActive = row.index === activeIndex
          const isSelected = seg.id === selectedId
          const editing = open?.id === seg.id && open.kind === 'text'
          const menuOpen = open?.id === seg.id && open.kind === 'speaker'
          const close = () => setOpen(null)
          return (
            // 高さは中身に任せて measureElement で測る(編集欄を開くと行が伸びる)
            <div
              key={seg.id}
              data-testid={`segment-${seg.idx}`}
              data-active={isActive || undefined}
              data-index={row.index}
              ref={virtualizer.measureElement}
              tabIndex={0}
              onClick={() => {
                selectSegment(seg.id)
                seekTo(seg.start)
              }}
              onDoubleClick={() => canEditText && setOpen({ id: seg.id, kind: 'text' })}
              onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return
                if (e.key === 'Enter') {
                  selectSegment(seg.id)
                  seekTo(seg.start)
                }
              }}
              className={[
                'group absolute left-0 w-full cursor-pointer border-b border-neutral-100 text-left text-sm dark:border-neutral-800',
                isActive
                  ? 'bg-blue-50 dark:bg-blue-950'
                  : 'hover:bg-neutral-50 dark:hover:bg-neutral-900',
                isSelected ? 'ring-1 ring-inset ring-blue-400' : '',
                seg.is_aizuchi ? 'opacity-40' : '',
              ].join(' ')}
              style={{ top: row.start }}
            >
              <div className="flex items-start gap-2 px-3 py-2">
                <span className="w-12 shrink-0 pt-0.5 font-mono text-xs text-neutral-400">
                  {formatTime(seg.start)}
                </span>
                {seg.speaker && (
                  <button
                    type="button"
                    data-testid={`speaker-${seg.idx}`}
                    title="話者名を変える・この行の話者を付け替える"
                    aria-expanded={menuOpen}
                    className={`inline-block shrink-0 rounded px-1.5 py-0.5 text-xs font-medium hover:ring-1 hover:ring-current ${speakerColor(seg.speaker)}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      setOpen(menuOpen ? null : { id: seg.id, kind: 'speaker' })
                    }}
                    onDoubleClick={(e) => e.stopPropagation()}
                  >
                    {seg.speaker}
                  </button>
                )}
                <span
                  className={[
                    'min-w-0 flex-1 break-words',
                    // 置換・修正が入った行は点線下線+ホバーで原文表示
                    seg.text !== seg.original_text
                      ? 'underline decoration-blue-400 decoration-dotted underline-offset-4'
                      : '',
                  ].join(' ')}
                  title={
                    seg.text !== seg.original_text
                      ? `原文: ${seg.original_text}`
                      : canEditText
                        ? 'ダブルクリックで文字を直せます'
                        : undefined
                  }
                >
                  {displayText(seg.text)}
                  {seg.edited_by_user && (
                    <span className="ml-1 align-middle text-xs text-amber-600">(編集済)</span>
                  )}
                </span>
                {canEditText && !editing && (
                  <button
                    type="button"
                    data-testid={`segment-edit-${seg.idx}`}
                    aria-label="この行の文字を直す"
                    title="この行の文字を直す(ダブルクリックでも直せます)"
                    className={`shrink-0 rounded p-0.5 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700 focus:opacity-100 dark:hover:bg-neutral-800 dark:hover:text-neutral-200 ${
                      isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                    }`}
                    onClick={(e) => {
                      e.stopPropagation()
                      setOpen({ id: seg.id, kind: 'text' })
                    }}
                  >
                    <PencilIcon />
                  </button>
                )}
              </div>
              {editing && <TextEditor seg={seg} handlers={handlers} onClose={close} />}
              {menuOpen && (
                <SpeakerMenu seg={seg} speakers={speakers} handlers={handlers} onClose={close} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
