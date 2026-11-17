/**
 * 書き出し先: 今どこに保存されるかを書き出す前に見せ、その場で変えられるようにする。
 *
 * 以前は「元動画の隣の exports/」に決まっていて、ファイル選択で取り込んだ動画だと
 * アプリのデータフォルダ(macOSなら ~/Library/Application Support/…。Finderでは
 * 隠れている)になり、書き出したのに見つけられなかった(issue #3)。
 *
 * - 「変更…」: デスクトップ版はOSのフォルダ選択(Finder / エクスプローラー)。
 *   ブラウザで動かす開発版は絶対パスを取れないので、パスの入力欄を出す
 * - 「フォルダを開く」: 書き出す前でも開ける(前に書き出した動画を探せる)
 * - 選んだ場所は全体の設定(export_dir)に覚える。次の書き出しからもそこに入る
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, errorText } from '../../api/client'
import { canPickFolder, pickFolder } from '../../lib/nativeDialog'
import { Button, selectCls } from '../ui'

const EXPORT_DIR_KEY = ['export-dir'] as const

export function ExportDestination({
  testId = 'export-destination',
  className = '',
}: {
  testId?: string
  className?: string
}) {
  const queryClient = useQueryClient()
  const dir = useQuery({ queryKey: EXPORT_DIR_KEY, queryFn: api.getExportDir })
  // フォルダ選択が無い環境で「変更…」を押したときの入力欄
  const [typing, setTyping] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (path: string) => api.updateSettings({ export_dir: path }),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      setTyping(null)
      return queryClient.invalidateQueries({ queryKey: EXPORT_DIR_KEY })
    },
  })
  const choose = useMutation({
    mutationFn: async () => {
      const picked = await pickFolder({
        title: '書き出した動画の保存先を選ぶ',
        defaultPath: dir.data?.path,
      })
      if (picked) await save.mutateAsync(picked)
    },
  })
  const reveal = useMutation({ mutationFn: api.revealExportDir })

  if (!dir.data) return null
  const busy = save.isPending || choose.isPending
  const error = save.error ?? choose.error ?? reveal.error

  return (
    <div
      data-testid={testId}
      className={`space-y-1.5 rounded-md border border-neutral-200 p-2 text-xs dark:border-neutral-800 ${className}`}
    >
      <div className="grid grid-cols-[auto_1fr] gap-x-2">
        <span className="text-neutral-500">保存先</span>
        {/* 選択してコピーできるよう、パスは文字として出す */}
        <span data-testid={`${testId}-path`} className="select-all break-all font-mono">
          {dir.data.path}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="ghost"
          className="px-2! py-1! text-xs!"
          data-testid={`${testId}-change`}
          disabled={busy}
          onClick={() => {
            save.reset()
            if (canPickFolder()) choose.mutate()
            else setTyping(dir.data.path)
          }}
        >
          変更…
        </Button>
        <Button
          variant="ghost"
          className="px-2! py-1! text-xs!"
          data-testid={`${testId}-reveal`}
          disabled={reveal.isPending}
          onClick={() => reveal.mutate()}
        >
          フォルダを開く
        </Button>
        {!dir.data.is_default && (
          <button
            type="button"
            data-testid={`${testId}-reset`}
            className="text-blue-600 hover:underline disabled:opacity-50"
            disabled={busy}
            title={dir.data.default_path}
            onClick={() => save.mutate('')}
          >
            既定の場所に戻す
          </button>
        )}
      </div>
      {typing !== null && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (typing.trim()) save.mutate(typing.trim())
          }}
        >
          <input
            data-testid={`${testId}-input`}
            aria-label="保存先のフォルダ"
            className={`${selectCls} min-w-0 flex-1 font-mono text-xs`}
            placeholder={dir.data.default_path}
            value={typing}
            onChange={(e) => setTyping(e.target.value)}
            autoFocus
          />
          <Button
            type="submit"
            className="px-2! py-1! text-xs!"
            data-testid={`${testId}-save`}
            disabled={busy || !typing.trim()}
          >
            保存
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="px-2! py-1! text-xs!"
            onClick={() => setTyping(null)}
          >
            やめる
          </Button>
        </form>
      )}
      {error && (
        <p data-testid={`${testId}-error`} className="text-red-600">
          {errorText(error)}
        </p>
      )}
    </div>
  )
}

/** 全体の設定に置く「書き出し先」の枠 */
export function ExportDestinationPanel() {
  return (
    <section
      data-testid="export-dir-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-1 text-sm font-semibold">書き出し先</h3>
      <p className="mb-2 text-xs text-neutral-500">
        書き出した動画はすべてこのフォルダに入ります。クリップの書き出しの横からも変えられます。
      </p>
      <ExportDestination testId="settings-export-destination" className="border-0! p-0!" />
    </section>
  )
}
