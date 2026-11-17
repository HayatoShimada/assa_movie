/**
 * 新しい版のお知らせ(ホームの上)と、全体の設定の「このアプリについて」。
 *
 * アプリに自動更新は無い。新しい版に気付けず、既に直っている不具合を古い版で
 * 踏み続ける人が出た(issue #3)。起動して最初に開くホームで知らせ、
 * ダウンロードページを開くボタンと入れ直しの手順を添える。
 *
 * ダウンロードページはバックエンドが既定のブラウザで開く(webviewの中のリンクは
 * 外のブラウザで開かないため)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, errorText, type UpdateStatus } from '../../api/client'
import { dismiss, isDismissed, UPDATE_KEEPS_DATA, UPDATE_STEPS } from '../../lib/update'
import { Button } from '../ui'

const UPDATE_KEY = ['update'] as const

function Steps() {
  return (
    <div data-testid="update-steps" className="space-y-1">
      <ol className="list-decimal space-y-0.5 pl-5">
        <li>「ダウンロードページを開く」から、お使いのOSのインストーラをダウンロードします。</li>
        <li>このアプリを閉じます。</li>
        <li>
          インストーラで入れ直します。
          <ul className="mt-0.5 list-disc pl-4">
            {UPDATE_STEPS.map((s) => (
              <li key={s.os}>
                <span className="font-semibold">{s.os}</span>: {s.step}
              </li>
            ))}
          </ul>
        </li>
      </ol>
      <p>{UPDATE_KEEPS_DATA}</p>
    </div>
  )
}

function OpenPageButton({ testId }: { testId: string }) {
  const open = useMutation({ mutationFn: api.openUpdatePage })
  return (
    <>
      <Button data-testid={testId} disabled={open.isPending} onClick={() => open.mutate()}>
        ダウンロードページを開く
      </Button>
      {open.isError && <span className="text-red-600">{errorText(open.error)}</span>}
    </>
  )
}

/** ホームの上に出す帯。新しい版が無い・確認していない・「あとで」済みなら何も描かない */
export function UpdateBanner({ className = 'mb-4' }: { className?: string }) {
  const update = useQuery({
    queryKey: UPDATE_KEY,
    queryFn: () => api.getUpdate(),
    staleTime: Infinity, // 起動中に1回(バックエンドも1回しか尋ねない)
    retry: false,
  })
  const [closed, setClosed] = useState(false)
  const u = update.data
  if (!u?.has_update || closed || isDismissed(u.latest)) return null

  return (
    <section
      data-testid="update-banner"
      className={`space-y-2 rounded-lg border border-blue-300 bg-blue-50 p-3 text-sm dark:border-blue-800 dark:bg-blue-950 ${className}`}
    >
      <p className="font-semibold">
        新しい版 <span data-testid="update-latest">v{u.latest}</span> があります
        <span className="ml-2 font-normal text-neutral-500">(お使いの版: v{u.current})</span>
      </p>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <OpenPageButton testId="update-open" />
        <Button
          variant="ghost"
          data-testid="update-later"
          onClick={() => {
            if (u.latest) dismiss(u.latest)
            setClosed(true)
          }}
        >
          あとで
        </Button>
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer text-neutral-600 dark:text-neutral-300">
          更新の手順と変更点
        </summary>
        <div className="mt-2 space-y-2">
          <Steps />
          {u.notes && (
            <pre
              data-testid="update-notes"
              className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded bg-white/70 p-2 font-sans dark:bg-black/30"
            >
              {u.notes}
            </pre>
          )}
        </div>
      </details>
    </section>
  )
}

function statusText(u: UpdateStatus): string {
  if (u.error) return u.error
  if (u.has_update) return `新しい版 v${u.latest} があります`
  if (u.checked && u.latest) return '最新の版です'
  if (u.checked) return '公開されている版を確認できませんでした'
  return '未確認(起動時の確認を切っています)'
}

/** 全体の設定の「このアプリについて」: 今の版・更新の確認・手順 */
export function AboutPanel() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const update = useQuery({
    queryKey: UPDATE_KEY,
    queryFn: () => api.getUpdate(),
    staleTime: Infinity,
    retry: false,
  })
  const checkNow = useMutation({
    mutationFn: () => api.getUpdate(true),
    onSuccess: (data) => queryClient.setQueryData(UPDATE_KEY, data),
  })
  // その場で保存する(下書き→保存の設定項目とは別。切った瞬間から通信しない)
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.updateSettings({ update_check_enabled: enabled }),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      return queryClient.invalidateQueries({ queryKey: UPDATE_KEY })
    },
  })

  const [choice, setChoice] = useState<boolean | null>(null)

  const u = update.data
  if (!u) return null
  // 押した瞬間に見た目を切り替える。保存の応答を待ってから切り替えると、
  // その間チェックが元に戻って「効いていない」ように見える
  const enabled = choice ?? settings.data?.values.update_check_enabled !== false

  return (
    <section
      data-testid="about-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-2 text-sm font-semibold">このアプリについて(更新)</h3>
      <div className="flex justify-between gap-3 text-sm">
        <span className="text-neutral-500">お使いの版</span>
        <span data-testid="about-version" className="font-medium">
          v{u.current}
        </span>
      </div>
      <div className="flex justify-between gap-3 text-sm">
        <span className="text-neutral-500">更新</span>
        <span
          data-testid="about-update-status"
          className={`text-right font-medium ${
            u.has_update
              ? 'text-blue-700 dark:text-blue-300'
              : u.error
                ? 'text-amber-700 dark:text-amber-400'
                : ''
          }`}
        >
          {statusText(u)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <Button
          variant="ghost"
          data-testid="about-check-now"
          disabled={checkNow.isPending}
          onClick={() => checkNow.mutate()}
        >
          {checkNow.isPending ? '確認中…' : '今すぐ確認'}
        </Button>
        {u.has_update && <OpenPageButton testId="about-open" />}
      </div>
      <label className="mt-2 flex items-start gap-2 text-xs">
        <input
          type="checkbox"
          data-testid="about-auto-check"
          className="mt-0.5"
          checked={enabled}
          disabled={toggle.isPending}
          onChange={(e) => {
            setChoice(e.target.checked)
            toggle.mutate(e.target.checked, { onSettled: () => setChoice(null) })
          }}
        />
        <span>
          起動時に新しい版を確認する
          <span className="block text-neutral-500">
            GitHub に「最新の版は?」と尋ねるだけで、動画・文字起こし・利用者の情報は送りません。
          </span>
        </span>
      </label>
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-neutral-600 dark:text-neutral-300">
          更新の手順
        </summary>
        <div className="mt-2">
          <Steps />
        </div>
      </details>
    </section>
  )
}
