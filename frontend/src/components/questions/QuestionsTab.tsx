/**
 * 質問キュー: LLMからの質問(固有名詞の表記確認)に答える。
 * 回答すると全出現箇所が一括修正され、用語集に登録される。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Question } from '../../api/client'
import { usePlayback } from '../../stores/playback'
import { useJobProgress } from '../../hooks/useJobProgress'
import { Button, ProgressBar } from '../ui'

function QuestionCard({
  question,
  mediaId,
  onAnswered,
}: {
  question: Question
  mediaId: number
  onAnswered: (message: string) => void
}) {
  const queryClient = useQueryClient()
  const seekTo = usePlayback((s) => s.seekTo)
  const [custom, setCustom] = useState('')

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['questions', mediaId] })
    queryClient.invalidateQueries({ queryKey: ['segments'] })
    queryClient.invalidateQueries({ queryKey: ['edits'] })
  }
  const answer = useMutation({
    mutationFn: (text: string) => api.answerQuestion(question.id, text),
    onSuccess: (res) => {
      // 回答するとカード自体がリストから消えるため、結果表示は親に渡す
      onAnswered(`${res.segments_changed}箇所を修正し、用語集に登録しました`)
      invalidate()
    },
  })
  const dismiss = useMutation({ mutationFn: () => api.dismissQuestion(question.id), onSuccess: invalidate })

  const jump = useMutation({
    mutationFn: async () => {
      const term = (question.target as { term?: string }).term
      if (!term) return
      const segments = await api.listSegments(mediaId)
      const hit = segments.find((s) => s.text.includes(term))
      if (hit) seekTo(hit.start)
    },
  })

  return (
    <div
      data-testid={`question-${question.id}`}
      className="border-b border-neutral-100 p-3 dark:border-neutral-800"
    >
      <p className="text-sm">{question.question_text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {question.candidates.map((c) => (
          <Button key={c} onClick={() => answer.mutate(c)} disabled={answer.isPending}>
            {c}
          </Button>
        ))}
        <form
          className="flex gap-1"
          onSubmit={(e) => {
            e.preventDefault()
            if (custom.trim()) answer.mutate(custom.trim())
          }}
        >
          <input
            className="w-32 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            placeholder="自由入力"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
          />
          <Button type="submit" variant="ghost" disabled={!custom.trim()}>
            回答
          </Button>
        </form>
        <button
          type="button"
          className="text-xs text-blue-600 hover:underline"
          onClick={() => jump.mutate()}
        >
          出現箇所へ
        </button>
        <button
          type="button"
          className="ml-auto text-xs text-neutral-400 hover:underline"
          onClick={() => dismiss.mutate()}
        >
          この質問を却下
        </button>
      </div>
    </div>
  )
}

export function QuestionsTab({ mediaId }: { mediaId: number }) {
  const queryClient = useQueryClient()
  const questions = useQuery({
    queryKey: ['questions', mediaId],
    queryFn: () => api.listQuestions(mediaId),
  })
  const [jobId, setJobId] = useState<number | null>(null)
  const progress = useJobProgress(jobId, () =>
    queryClient.invalidateQueries({ queryKey: ['questions', mediaId] }),
  )
  const scan = useMutation({
    mutationFn: () => api.createJob(mediaId, 'extract_terms', {}),
    onSuccess: (job) => setJobId(job.id),
  })
  const running = progress.status === 'running' || progress.status === 'queued'
  const [lastResult, setLastResult] = useState<string | null>(null)

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="space-y-2 border-b border-neutral-200 p-3 dark:border-neutral-800">
        <Button data-testid="run-scan" disabled={running} onClick={() => scan.mutate()}>
          固有名詞をスキャン
        </Button>
        {jobId !== null && progress.status !== 'idle' && (
          <ProgressBar
            value={progress.progress}
            label={progress.status === 'completed' ? 'スキャン完了' : 'スキャン中...'}
          />
        )}
      </div>
      {lastResult && (
        <p className="border-b border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
          {lastResult}
        </p>
      )}
      {questions.data?.length === 0 && (
        <p className="p-3 text-sm text-neutral-500">
          未回答の質問はありません。「固有名詞をスキャン」で表記が怪しい語を探せます。
        </p>
      )}
      {questions.data?.map((q) => (
        <QuestionCard key={q.id} question={q} mediaId={mediaId} onAnswered={setLastResult} />
      ))}
    </div>
  )
}
