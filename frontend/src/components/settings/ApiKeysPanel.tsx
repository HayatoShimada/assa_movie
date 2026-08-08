/**
 * APIキーのパネル(設定タブ)。
 *
 * キーはこの端末に保存するだけで、どこにも送らない。
 * 登録済みかどうかと末尾4文字だけを表示する(全文を画面に出す必要が無い)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, api, type ApiKeyStatus } from '../../api/client'
import { Button, selectCls } from '../ui'

function KeyRow({
  provider,
  status,
  onSaved,
}: {
  provider: string
  status: ApiKeyStatus
  onSaved: (keys: Record<string, ApiKeyStatus>) => void
}) {
  const [key, setKey] = useState('')
  const save = useMutation({
    mutationFn: (value: string) => api.registerApiKey(provider, value),
    onSuccess: (data) => {
      onSaved(data)
      setKey('')
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteApiKey(provider),
    onSuccess: onSaved,
  })
  // 環境変数のキーはファイルを消しても残るので、削除ボタンを出さない
  const removable = status.configured && status.source !== '環境変数'

  return (
    <div className="border-t border-neutral-200 py-2 first:border-t-0 dark:border-neutral-800">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium">{status.label}</span>
        <span className="text-xs text-neutral-500">
          {status.configured ? `登録済み ${status.hint}(${status.source})` : '未登録'}
        </span>
      </div>
      <div className="mt-2 flex gap-2">
        <input
          data-testid={`apikey-input-${provider}`}
          type="password"
          autoComplete="off"
          className={`${selectCls} flex-1 font-mono text-xs`}
          placeholder={status.configured ? '新しいキーで置き換える' : 'APIキーを貼り付け'}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <Button
          data-testid={`apikey-save-${provider}`}
          type="button"
          onClick={() => save.mutate(key)}
          disabled={!key.trim() || save.isPending}
        >
          保存
        </Button>
        {removable && (
          <Button
            data-testid={`apikey-delete-${provider}`}
            type="button"
            variant="ghost"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
          >
            削除
          </Button>
        )}
      </div>
      {save.isError && (
        <p data-testid={`apikey-error-${provider}`} className="mt-1 text-xs text-red-600">
          {save.error instanceof ApiError ? save.error.detail : '保存できませんでした'}
        </p>
      )}
    </div>
  )
}

export function ApiKeysPanel() {
  const queryClient = useQueryClient()
  const keys = useQuery({ queryKey: ['keys'], queryFn: api.getApiKeys })
  if (!keys.data) return null

  const onSaved = (data: Record<string, ApiKeyStatus>) => {
    queryClient.setQueryData(['keys'], data)
    // プロバイダの選択可否(ready)がキーの有無で変わるので取り直す
    queryClient.invalidateQueries({ queryKey: ['settings'] })
  }

  return (
    <section
      data-testid="apikeys-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-1 text-sm font-semibold">クラウドLLMのAPIキー</h3>
      <p className="mb-2 text-xs text-neutral-500">
        この端末にだけ保存します。クラウドLLMを選ぶと、文字起こしがその提供元に送信されます。
      </p>
      {Object.entries(keys.data).map(([provider, status]) => (
        <KeyRow key={provider} provider={provider} status={status} onSaved={onSaved} />
      ))}
    </section>
  )
}
