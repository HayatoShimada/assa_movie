/**
 * APIキーのパネル(設定タブ)。
 *
 * 保存前にバックエンドが提供元のAPIへ接続してキーの有効性を確かめる
 * (形式は仕様変更で変わるため、接頭辞では判定しない)。それ以外には送らない。
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
  idPrefix = 'apikey',
}: {
  provider: string
  status: ApiKeyStatus
  onSaved: (keys: Record<string, ApiKeyStatus>) => void
  /** data-testidの接頭辞。同じ画面にパネルとインライン登録が並ぶため分ける */
  idPrefix?: string
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
          data-testid={`${idPrefix}-input-${provider}`}
          type="password"
          autoComplete="off"
          className={`${selectCls} flex-1 font-mono text-xs`}
          placeholder={status.configured ? '新しいキーで置き換える' : 'APIキーを貼り付け'}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <Button
          data-testid={`${idPrefix}-save-${provider}`}
          type="button"
          onClick={() => save.mutate(key)}
          disabled={!key.trim() || save.isPending}
        >
          {save.isPending ? '確認中…' : '保存'}
        </Button>
        {removable && (
          <Button
            data-testid={`${idPrefix}-delete-${provider}`}
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
        <p data-testid={`${idPrefix}-error-${provider}`} className="mt-1 text-xs text-red-600">
          {save.error instanceof ApiError ? save.error.detail : '保存できませんでした'}
        </p>
      )}
    </div>
  )
}

/** キー保存後の共通処理を返す(キャッシュ更新+プロバイダのready再取得) */
function useOnKeySaved() {
  const queryClient = useQueryClient()
  return (data: Record<string, ApiKeyStatus>) => {
    queryClient.setQueryData(['keys'], data)
    // プロバイダの選択可否(ready)がキーの有無で変わるので取り直す
    queryClient.invalidateQueries({ queryKey: ['settings'] })
  }
}

/**
 * LLMセクション用のインラインキー登録。
 *
 * プロバイダ選択肢に「(APIキー未設定)」と出ても、どこで登録するのか
 * 分からなかった。選ぶその場に動線を置く:
 * - 未登録のクラウドプロバイダは常に出す(登録できないと選べない)
 * - 選択中のクラウドプロバイダは登録済みでも出す(状態確認・差し替え・削除)
 * プロジェクト設定・新規プロジェクト画面にはキーのパネルが無いので、
 * ここが唯一の動線になる。
 */
export function CloudKeySetup({
  providers,
  selected,
}: {
  providers: string[]
  /** 現在選択中のLLMプロバイダ(ローカルならインラインに出ない) */
  selected?: string
}) {
  const keys = useQuery({ queryKey: ['keys'], queryFn: api.getApiKeys })
  const onSaved = useOnKeySaved()
  if (!keys.data) return null
  const visible = providers.filter(
    (p) => keys.data[p] && (!keys.data[p].configured || p === selected),
  )
  if (visible.length === 0) return null

  return (
    <div
      data-testid="llm-key-setup"
      className="my-2 rounded-md border border-dashed border-neutral-300 p-2 dark:border-neutral-700"
    >
      <p className="text-xs text-neutral-500">
        クラウドLLMはAPIキーを登録すると選べます(有効性を確認してこの端末にだけ保存)。
      </p>
      {visible.map((provider) => (
        <KeyRow
          key={provider}
          provider={provider}
          status={keys.data[provider]}
          onSaved={onSaved}
          idPrefix="llmkey"
        />
      ))}
    </div>
  )
}

export function ApiKeysPanel() {
  const keys = useQuery({ queryKey: ['keys'], queryFn: api.getApiKeys })
  const onSaved = useOnKeySaved()
  if (!keys.data) return null

  return (
    <section
      data-testid="apikeys-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-1 text-sm font-semibold">クラウドLLMのAPIキー</h3>
      <p className="mb-2 text-xs text-neutral-500">
        保存する前にキーが有効か提供元へ接続して確認し、この端末にだけ保存します。
        クラウドLLMを選ぶと、文字起こしがその提供元に送信されます。
      </p>
      {Object.entries(keys.data).map(([provider, status]) => (
        <KeyRow key={provider} provider={provider} status={status} onSaved={onSaved} />
      ))}
    </section>
  )
}
