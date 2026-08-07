/**
 * ジョブ進捗をSSEで購読するフック。
 * ジョブが終端状態(completed/failed)になったら自動で切断し、onDone を呼ぶ。
 */
import { useEffect, useRef, useState } from 'react'
import { subscribeJob, type Job } from '../api/client'

export interface JobProgress {
  status: Job['status'] | 'idle'
  progress: number
  error: string | null
}

export function useJobProgress(jobId: number | null, onDone?: (job: Job) => void) {
  const [state, setState] = useState<JobProgress>({ status: 'idle', progress: 0, error: null })
  // onDoneの変化で再購読しないようrefに逃がす
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    if (jobId === null) {
      setState({ status: 'idle', progress: 0, error: null })
      return
    }
    const stop = subscribeJob(jobId, (job) => {
      setState({ status: job.status, progress: job.progress, error: job.error ?? null })
      if (job.status === 'completed' || job.status === 'failed') {
        onDoneRef.current?.(job)
      }
    })
    return stop
  }, [jobId])

  return state
}
