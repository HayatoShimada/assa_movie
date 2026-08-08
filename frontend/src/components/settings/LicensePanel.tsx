/**
 * ライセンスパネル(設定タブ)。
 *
 * 検証はバックエンドがローカルで行う(通信は一切しない)。
 * 状態を出すのと、キーを貼って登録するだけの画面。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, api, type LicenseStatus } from '../../api/client'
import { Button, selectCls } from '../ui'

const STATUS_LABEL: Record<LicenseStatus['status'], string> = {
  valid: '有効',
  grace: '期限切れ(猶予期間中)',
  expired: '期限切れ',
  invalid: 'キーが正しくありません',
  missing: '未登録',
}

const STATUS_STYLE: Record<LicenseStatus['status'], string> = {
  valid: 'text-green-700 dark:text-green-400',
  grace: 'text-amber-700 dark:text-amber-400',
  expired: 'text-red-600 dark:text-red-400',
  invalid: 'text-red-600 dark:text-red-400',
  missing: 'text-neutral-500',
}

/** 状態に応じて出す一言。何をすればいいかだけ書く */
function guidance(license: LicenseStatus): string | null {
  if (license.status === 'missing') return 'ライセンスキーを登録してください。'
  if (license.status === 'grace') {
    return `猶予期間中です。あと${(license.days_left ?? 0) + 30}日で使えなくなります。更新版のキーをご登録ください。`
  }
  if (license.status === 'expired') return '更新版のキーをご登録ください。'
  if (license.expiring_soon) return `有効期限まであと${license.days_left}日です。`
  return null
}

export function LicensePanel() {
  const queryClient = useQueryClient()
  const license = useQuery({ queryKey: ['license'], queryFn: api.getLicense })
  const [key, setKey] = useState('')
  const register = useMutation({
    mutationFn: api.registerLicense,
    onSuccess: (data) => {
      queryClient.setQueryData(['license'], data)
      setKey('')
    },
  })

  if (!license.data) return null
  const current = license.data
  const note = guidance(current)

  return (
    <section
      data-testid="license-panel"
      className="mb-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="mb-2 text-sm font-semibold">ライセンス</h3>

      <div className="flex justify-between gap-3 text-sm">
        <span className="text-neutral-500">状態</span>
        <span data-testid="license-status" className={`font-medium ${STATUS_STYLE[current.status]}`}>
          {STATUS_LABEL[current.status]}
        </span>
      </div>
      {current.licensee && (
        <div className="flex justify-between gap-3 text-sm">
          <span className="text-neutral-500">ライセンシー</span>
          <span className="font-medium">{current.licensee}</span>
        </div>
      )}
      {current.expires && (
        <div className="flex justify-between gap-3 text-sm">
          <span className="text-neutral-500">有効期限</span>
          <span className="font-medium">{current.expires}</span>
        </div>
      )}
      {note && (
        <p data-testid="license-note" className="mt-2 text-xs text-amber-700 dark:text-amber-400">
          {note}
        </p>
      )}

      <div className="mt-3 flex gap-2">
        <input
          data-testid="license-key-input"
          className={`${selectCls} flex-1 font-mono text-xs`}
          placeholder="KS1.… で始まるキーを貼り付け"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <Button
          data-testid="license-register"
          type="button"
          onClick={() => register.mutate(key)}
          disabled={!key.trim() || register.isPending}
        >
          {register.isPending ? '確認中…' : '登録'}
        </Button>
      </div>
      {register.isError && (
        <p data-testid="license-error" className="mt-2 text-xs text-red-600">
          {register.error instanceof ApiError ? register.error.detail : '登録できませんでした'}
        </p>
      )}
      <p className="mt-2 text-xs text-neutral-500">
        確認はこの端末の中だけで行います(ネットワークには接続しません)。
      </p>
    </section>
  )
}
