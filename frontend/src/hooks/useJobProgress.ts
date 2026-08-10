/**
 * ジョブ進捗をSSEで購読するフック。
 * ジョブが終端状態(completed/failed)になったら自動で切断し、onDone を呼ぶ。
 */
import { useEffect, useRef, useState } from 'react'
import { subscribeJob, type Job } from '../api/client'

export interface JobProgress {
  status: Job['status'] | 'idle'
  progress: number
  /** いま何をしているか(「話者分離中」等)。実行中のみ届く */
  phase: string | null
  error: string | null
}

const IDLE: JobProgress = { status: 'idle', progress: 0, phase: null, error: null }

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
    const stop = subscribeJob(jobId, (job) => {
      setState({
        status: job.status,
        progress: job.progress,
        phase: job.phase ?? null,
        error: job.error ?? null,
      })
      if (['completed', 'failed', 'cancelled'].includes(job.status)) {
        onDoneRef.current?.(job)
      }
    })
    return stop
  }, [jobId])

  return state
}
