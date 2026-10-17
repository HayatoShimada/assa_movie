/**
 * ジョブ進捗をSSEで購読するフック。
 * ジョブが終端状態(completed/failed/cancelled)になったら自動で切断し、onDone を呼ぶ。
 *
 * 途中でSSEが切れたら(バックエンドの再起動・スリープ復帰など)ジョブを取り直し、
 * まだ終わっていなければ購読し直す。切れたまま放っておくと、失敗していても
 * 「〜中」のまま画面が固まる。
 */
import { useEffect, useRef, useState } from 'react'
import { ApiError, api, isJobDone, subscribeJob, type Job } from '../api/client'

export interface JobProgress {
  status: Job['status'] | 'idle'
  progress: number
  /** いま何をしているか(「話者分離中」等)。実行中のみ届く */
  phase: string | null
  error: string | null
  /** ジョブの結果(SSEが送ってくれば。件数や完了時の説明など) */
  result: Job['result']
}

const IDLE: JobProgress = { status: 'idle', progress: 0, phase: null, error: null, result: null }

/** 切れてから購読し直すまでの間隔 */
const RESUBSCRIBE_MS = 2000

export function useJobProgress(jobId: number | null, onDone?: (job: Job) => void) {
  const [state, setState] = useState<JobProgress>(IDLE)
  // onDoneの変化で再購読しないようrefに逃がす
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    if (jobId === null) {
      setState(IDLE)
      return
    }
    let stopped = false
    let stop: () => void = () => {}
    let timer: ReturnType<typeof setTimeout> | undefined

    const apply = (job: Job) => {
      if (stopped) return
      setState({
        status: job.status,
        progress: job.progress,
        phase: job.phase ?? null,
        error: job.error ?? null,
        result: job.result ?? null,
      })
      if (isJobDone(job.status)) onDoneRef.current?.(job)
    }

    const recover = async () => {
      if (stopped) return
      try {
        const job = await api.getJob(jobId)
        apply(job)
        if (isJobDone(job.status)) return
      } catch (e) {
        if (stopped) return
        // 消えたジョブ(動画ごと削除された等)は待っても戻らない
        if (e instanceof ApiError && e.status === 404) {
          setState({ ...IDLE, status: 'failed', error: 'ジョブが見つかりません' })
          return
        }
      }
      if (!stopped) timer = setTimeout(listen, RESUBSCRIBE_MS)
    }

    const listen = () => {
      if (stopped) return
      stop = subscribeJob(jobId, apply, () => void recover())
    }

    listen()
    return () => {
      stopped = true
      clearTimeout(timer)
      stop()
    }
  }, [jobId])

  return state
}
