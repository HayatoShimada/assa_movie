/**
 * セットアップパネル(設定タブ)。
 *
 * インストール版のユーザーはターミナルを開かないので、
 * 何が足りていて何が足りないかを画面で示し、取れるものはここから取る。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, subscribeJob, type SetupItem } from '../../api/client'
import { Button } from '../ui'

/** 3.1GBを「3100MB」と出すと大きさが伝わらない */
function formatSize(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)}GB` : `${mb}MB`
}

/** 1項目ぶんの取得UI。初回セットアップのウィザードからも使う(components/setup/) */
export function SetupItemRow({ id, item }: { id: string; item: SetupItem }) {
  const queryClient = useQueryClient()
  const [progress, setProgress] = useState<number | null>(null)

  const fetchModel = useMutation({
    mutationFn: async () => {
      const job = await api.createSetupJob(id)
      setProgress(0)
      // 完了までSSEで進捗を受ける(数十MBのダウンロードなのでバーが要る)
      await new Promise<void>((resolve) => {
        const stop = subscribeJob(job.id, (j) => {
          setProgress(j.progress)
          if (j.status === 'succeeded' || j.status === 'failed') {
            stop()
            resolve()
          }
        })
      })
    },
    onSettled: () => {
      setProgress(null)
      queryClient.invalidateQueries({ queryKey: ['setup'] })
      // 話者分離エンジンの選択可否が変わる
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  return (
    <div
      data-testid={`setup-item-${id}`}
      className="border-t border-neutral-200 py-2 first:border-t-0 dark:border-neutral-800"
    >
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium">{item.label}</span>
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
            disabled={fetchModel.isPending}
          >
            {progress === null ? 'ダウンロード' : `取得中… ${Math.round(progress * 100)}%`}
          </Button>
          {fetchModel.isError && (
            <p data-testid={`setup-error-${id}`} className="mt-1 text-xs text-red-600">
              取得できませんでした。ネットワークを確認して、もう一度お試しください。
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
  // 全部そろっていれば出す必要が無い
  if (Object.values(setup.data).every((item) => item.ready)) return null

  return (
    <section
      data-testid="setup-panel"
      className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/30"
    >
      <h3 className="mb-1 text-sm font-semibold">セットアップ</h3>
      <p className="mb-2 text-xs text-neutral-600 dark:text-neutral-400">
        足りていないものがあります。無くても文字起こしはできますが、揃えると精度と速度が上がります。
      </p>
      {Object.entries(setup.data).map(([id, item]) => (
        <SetupItemRow key={id} id={id} item={item} />
      ))}
    </section>
  )
}
