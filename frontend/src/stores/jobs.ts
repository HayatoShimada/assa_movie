/**
 * 画面から始めたジョブIDのストア(枠の名前は lib/jobs.ts の jobSlots)。
 *
 * タブのコンポーネントのstateに持つと、タブ切替のアンマウントで消える。
 * ここに預けておけば、戻ったときに同じジョブの進捗(終わっていれば完了・失敗)を出せる。
 * 再読み込みでは消えるが、実行中のものは GET /api/jobs/active から拾い直す(useTrackedJob)。
 */
import { create } from 'zustand'

interface JobStore {
  jobIds: Record<string, number>
  setJobId: (key: string, jobId: number) => void
}

export const useJobStore = create<JobStore>((set) => ({
  jobIds: {},
  setJobId: (key, jobId) => set((s) => ({ jobIds: { ...s.jobIds, [key]: jobId } })),
}))
