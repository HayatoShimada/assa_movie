/**
 * 書き出し結果: 保存先(フォルダとファイル名)・「フォルダを開く」・「再生」。
 *
 * 「書き出し完了」だけでは、どこに保存されたか利用者には分からない
 * (ファイル選択で取り込んだ動画はアプリのデータフォルダに書き出される)。
 * フォルダはバックエンドがOSのファイラーで開く(デスクトップ版とブラウザ版の
 * どちらでも動く)。再生は画面内で行う。
 */
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, api } from '../../api/client'
import { splitPath } from '../../lib/media'
import { Button } from '../ui'

/** APIのエラー本文(FastAPIの {"detail": ...})から利用者に見せる文を取り出す */
function errorText(error: unknown): string {
  if (!(error instanceof ApiError)) return String(error)
  try {
    const body = JSON.parse(error.detail) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // JSONでなければ本文をそのまま見せる
  }
  return error.detail
}

export function ExportResult({
  jobId,
  path,
  testId,
}: {
  jobId: number
  path: string
  testId: string
}) {
  const { folder, name } = splitPath(path)
  const [playing, setPlaying] = useState(false)
  const reveal = useMutation({ mutationFn: () => api.revealExport(jobId) })

  return (
    <div
      data-testid={testId}
      className="space-y-2 rounded-md border border-emerald-300 bg-emerald-50 p-2 text-xs dark:border-emerald-800 dark:bg-emerald-950"
    >
      <p className="font-semibold text-emerald-800 dark:text-emerald-200">書き出しました</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
        <dt className="text-neutral-500">ファイル名</dt>
        <dd data-testid={`${testId}-name`} className="break-all font-mono">
          {name}
        </dd>
        <dt className="text-neutral-500">保存先</dt>
        {/* 選択してコピーできるよう、パスは文字として出す */}
        <dd data-testid={`${testId}-folder`} className="select-all break-all font-mono">
          {folder}
        </dd>
      </dl>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="ghost"
          data-testid={`${testId}-reveal`}
          disabled={reveal.isPending}
          onClick={() => reveal.mutate()}
        >
          フォルダを開く
        </Button>
        <Button
          variant="ghost"
          data-testid={`${testId}-play`}
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? '再生を閉じる' : '再生'}
        </Button>
      </div>
      {reveal.isError && <p className="text-red-600">{errorText(reveal.error)}</p>}
      {playing && (
        <video
          data-testid={`${testId}-video`}
          className="max-h-96 w-full rounded bg-black"
          src={api.exportOutputUrl(jobId)}
          controls
          autoPlay
        />
      )}
    </div>
  )
}
