/**
 * 画面の操作ひとつ分のジョブを追うフック。
 *
 * useJobProgress はジョブIDを受け取るだけなので、IDを呼び出し側のstateに持つと
 * タブ切替や再読み込みで失い、処理中なのに進捗が消えてボタンがまた押せた。
 * ここではIDをストアに預け、無ければ実行中のジョブから拾い直す(lib/jobs.ts)。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api, type Job } from '../api/client'
import { isJobBusy, pickJobId, type JobSlot } from '../lib/jobs'
import { useJobStore } from '../stores/jobs'
import { useJobProgress } from './useJobProgress'

export const ACTIVE_JOBS_KEY = ['jobs', 'active'] as const

export function useTrackedJob(slot: JobSlot, onDone?: (job: Job) => void) {
  const queryClient = useQueryClient()
  const stored = useJobStore((s) => s.jobIds[slot.key])
  const setJobId = useJobStore((s) => s.setJobId)
  // マウントのたびに取り直す(既定の staleTime 0)。同じキーなので複数の枠で1回にまとまる
  const active = useQuery({ queryKey: ACTIVE_JOBS_KEY, queryFn: api.listActiveJobs })
  const activeJobs = active.data ?? []

  const jobId = pickJobId(stored, activeJobs, slot)
  // 拾い直したIDも預ける(実行中の一覧から消えた後も完了・失敗を出し続けるため)
  useEffect(() => {
    if (jobId !== null && jobId !== stored) setJobId(slot.key, jobId)
  }, [jobId, stored, setJobId, slot.key])

  const progress = useJobProgress(jobId, (job) => {
    queryClient.invalidateQueries({ queryKey: ACTIVE_JOBS_KEY })
    onDone?.(job)
  })

  return {
    jobId,
    progress,
    /** 実行中・順番待ち。ボタンを押せなくするのに使う */
    busy: isJobBusy(progress.status, jobId, activeJobs),
    /** 始めたジョブを預ける */
    start: (id: number) => {
      setJobId(slot.key, id)
      queryClient.invalidateQueries({ queryKey: ACTIVE_JOBS_KEY })
    },
  }
}
