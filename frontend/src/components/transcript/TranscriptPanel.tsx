/**
 * 文字起こしタブの中身: 手直しの案内 + セグメント一覧(手直しのAPIとの繋ぎ)。
 *
 * 行をクリックするとシークするだけで「直せる」ことに気付けなかった(v2.0の初心者評価)。
 * 一覧の上に1行で直し方を出し、各行にも鉛筆ボタンとホバー時の案内を付ける。
 */
import { useQueryClient } from '@tanstack/react-query'
import { api, type Segment } from '../../api/client'
import { SegmentList } from './SegmentList'

export function TranscriptPanel({ mediaId, segments }: { mediaId: number; segments: Segment[] }) {
  const queryClient = useQueryClient()
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['segments', mediaId] })
    // 手直しの取り消しでAIの修正が取り消し扱いになることがある(レビュータブの表示)
    queryClient.invalidateQueries({ queryKey: ['edits', mediaId] })
  }
  // 保存が済んでから一覧を取り直す(失敗はSegmentListが行の中に出す)
  const thenRefresh = async <T,>(p: Promise<T>) => {
    const r = await p
    refresh()
    return r
  }

  return (
    <div className="flex h-full flex-col">
      <p
        data-testid="transcript-hint"
        className="border-b border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400"
      >
        誤認識は、行をダブルクリック(または鉛筆ボタン)で直せます。話者名を押すと名前を変えられます。
      </p>
      <div className="min-h-0 flex-1">
        <SegmentList
          segments={segments}
          onSaveText={(seg, text) => thenRefresh(api.updateSegment(seg.id, { text }))}
          onRestore={(seg) => thenRefresh(api.restoreSegment(seg.id))}
          onSetSpeaker={(seg, speaker) => thenRefresh(api.updateSegment(seg.id, { speaker }))}
          onRenameSpeaker={(current, next) =>
            thenRefresh(api.renameSpeaker(mediaId, current, next))
          }
        />
      </div>
    </div>
  )
}
