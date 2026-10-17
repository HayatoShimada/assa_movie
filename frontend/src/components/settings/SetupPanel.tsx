/**
 * セットアップパネル(設定タブ)。
 *
 * インストール版のユーザーはターミナルを開かないので、
 * 何が足りていて何が足りないかを画面で示し、取れるものはここから取る。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type SetupItem } from '../../api/client'
import { useTrackedJob } from '../../hooks/useTrackedJob'
import { jobErrorMessage, jobSlots } from '../../lib/jobs'
import { Button } from '../ui'

/** 3.1GBを「3100MB」と出すと大きさが伝わらない */
function formatSize(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)}GB` : `${mb}MB`
}

/** 1項目ぶんの取得UI。初回セットアップのウィザードからも使う(components/setup/) */
export function SetupItemRow({ id, item }: { id: string; item: SetupItem }) {
  const queryClient = useQueryClient()
  // 完了までSSEで進捗を受ける(数十MBのダウンロードなのでバーが要る)。
  // ジョブIDは行の外に預ける。行のstateに持っていたときは、取得中にタブを
  // 切り替えて戻ると進捗が消え、もう一度押せて二重にダウンロードできた
  const job = useTrackedJob(jobSlots.setup(id), () => {
    queryClient.invalidateQueries({ queryKey: ['setup'] })
    // 話者分離エンジンの選択可否が変わる
    queryClient.invalidateQueries({ queryKey: ['settings'] })
  })
  const fetchModel = useMutation({
    mutationFn: () => api.createSetupJob(id),
    onSuccess: (j) => job.start(j.id),
  })
  const fetching = job.busy || fetchModel.isPending
  const failed = fetchModel.isError || job.progress.status === 'failed'
  // 失敗の理由はバックエンドの文言をそのまま添える(推測で言い換えない)
  const failure = fetchModel.isError
    ? fetchModel.error.message
    : jobErrorMessage(job.progress.error)

  return (
    <div
      data-testid={`setup-item-${id}`}
      className="border-t border-neutral-200 py-2 first:border-t-0 dark:border-neutral-800"
    >
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium">
          {item.label}
          {item.required && !item.ready && (
            <span className="ml-1 rounded bg-amber-200 px-1 text-xs text-amber-900 dark:bg-amber-800 dark:text-amber-100">
              必須
            </span>
          )}
        </span>
        <span
          data-testid={`setup-state-${id}`}
          className={item.ready ? 'text-xs text-green-700 dark:text-green-400' : 'text-xs text-neutral-500'}
        >
          {item.ready ? '準備できています' : `未取得(約${formatSize(item.size_mb)})`}
        </span>
      </div>
      <p className="mt-1 text-xs text-neutral-500">{item.note}</p>
      {!item.ready && item.installable && (
        <div className="mt-2">
          <Button
            data-testid={`setup-fetch-${id}`}
            type="button"
            onClick={() => fetchModel.mutate()}
            disabled={fetching}
          >
            {!fetching
              ? 'ダウンロード'
              : job.progress.status === 'queued'
                ? '順番待ち…'
                : `取得中… ${Math.round(job.progress.progress * 100)}%`}
          </Button>
          {failed && !fetching && (
            <p data-testid={`setup-error-${id}`} className="mt-1 text-xs text-red-600">
              取得できませんでした。ネットワークを確認して、もう一度お試しください。
              {failure && <span className="block break-all">{failure}</span>}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function SetupPanel() {
  const setup = useQuery({ queryKey: ['setup'], queryFn: api.getSetupStatus })
  if (!setup.data) return null
  const items = Object.values(setup.data)
  // 全部そろっていれば出す必要が無い
  if (items.every((item) => item.ready)) return null
  const blocking = items.some((item) => item.required && !item.ready)

  return (
    <section
      data-testid="setup-panel"
      className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/30"
    >
      <h3 className="mb-1 text-sm font-semibold">セットアップ</h3>
      <p className="mb-2 text-xs text-neutral-600 dark:text-neutral-400">
        {blocking
          ? 'この機体で文字起こしを始めるには、下の「必須」の項目を取得してください。'
          : '足りていないものがあります。無くても文字起こしはできますが、揃えると精度が上がります。'}
      </p>
      {Object.entries(setup.data).map(([id, item]) => (
        <SetupItemRow key={id} id={id} item={item} />
      ))}
    </section>
  )
}
