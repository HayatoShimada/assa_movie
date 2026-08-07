/**
 * 対話アシスト: 選択中のセグメントに自然言語で指示し、編集提案を受け取る。
 * 提案は通常のedits(proposed)なので、承認/却下はレビューAPIを使う。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type AssistResponse, type Segment } from '../../api/client'
import { Button } from '../ui'

export function AssistChat({ segment, projectId }: { segment: Segment; projectId?: number }) {
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [response, setResponse] = useState<AssistResponse | null>(null)
  const [promoted, setPromoted] = useState(false)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['edits'] })
    queryClient.invalidateQueries({ queryKey: ['segments'] })
  }
  const ask = useMutation({
    mutationFn: () => api.assistSegment(segment.id, message.trim()),
    onSuccess: (res) => {
      setResponse(res)
      setPromoted(false)
      setMessage('')
      invalidate() // 提案がeditsに入るのでレビュータブのバッジも更新
    },
  })
  const accept = useMutation({
    mutationFn: (editId: number) => api.acceptEdit(editId, {}),
    onSuccess: () => {
      setResponse(null)
      invalidate()
    },
  })
  const reject = useMutation({
    mutationFn: (editId: number) => api.rejectEdit(editId),
    onSuccess: () => {
      setResponse(null)
      invalidate()
    },
  })
  const promote = useMutation({
    mutationFn: (text: string) => api.createInstruction(projectId!, text),
    onSuccess: () => setPromoted(true),
  })

  return (
    <div
      data-testid="assist-chat"
      className="border-t border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900"
    >
      <p className="mb-1 truncate text-xs text-neutral-500" title={segment.text}>
        選択中: {segment.text}
      </p>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (message.trim()) ask.mutate()
        }}
      >
        <input
          data-testid="assist-input"
          className="flex-1 rounded border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          placeholder="AIに指示(例: この『それ』は文字起こしアプリのこと)"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <Button type="submit" disabled={ask.isPending || !message.trim()}>
          {ask.isPending ? '考え中...' : '送信'}
        </Button>
      </form>

      {ask.isError && <p className="mt-1 text-xs text-red-600">{String(ask.error.message)}</p>}

      {response && (
        <div data-testid="assist-response" className="mt-2 space-y-2">
          <p className="text-sm">{response.reply}</p>
          {response.edits.map((e) => (
            <div
              key={e.id}
              className="flex items-center gap-2 rounded border border-neutral-200 bg-white p-2 text-sm dark:border-neutral-700 dark:bg-neutral-950"
            >
              <span className="line-through opacity-60">{e.original}</span>
              <span className="text-neutral-400">→</span>
              <span className="font-medium">{e.replacement}</span>
              <span className="ml-auto flex gap-1">
                <Button className="!px-2 !py-0.5 text-xs" onClick={() => accept.mutate(e.id)}>
                  承認
                </Button>
                <Button
                  variant="ghost"
                  className="!px-2 !py-0.5 text-xs"
                  onClick={() => reject.mutate(e.id)}
                >
                  却下
                </Button>
              </span>
            </div>
          ))}
          {response.instruction_suggestion && projectId && !promoted && (
            <div className="flex items-center gap-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs dark:border-amber-800 dark:bg-amber-950">
              <span>今後も使うルールにしますか?「{response.instruction_suggestion}」</span>
              <Button
                className="!px-2 !py-0.5 text-xs"
                onClick={() => promote.mutate(response.instruction_suggestion!)}
              >
                カスタム指示に追加
              </Button>
            </div>
          )}
          {promoted && <p className="text-xs text-emerald-600">カスタム指示に追加しました</p>}
        </div>
      )}
    </div>
  )
}
