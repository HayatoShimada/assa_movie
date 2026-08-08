/**
 * 設定タブ(グローバル設定)。
 *
 * 変更はいったん下書きに溜め、保存ボタンでまとめて PATCH /api/settings する。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import type { SettingsValues } from '../../lib/settings'
import { EnvironmentPanel } from './EnvironmentPanel'
import { SaveBar } from './SaveBar'
import { SettingsFields } from './SettingsFields'

export function SettingsForm() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  // 保存前の変更(キー→値)。保存に成功したら空に戻す
  const [draft, setDraft] = useState<SettingsValues>({})
  const update = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      setDraft({})
    },
  })

  if (settings.isPending) return <p className="p-4 text-sm text-neutral-500">読み込み中...</p>
  if (settings.isError) return <p className="p-4 text-sm text-red-600">設定を取得できません</p>

  const dirty = Object.keys(draft).length > 0

  return (
    <div className="p-4">
      <EnvironmentPanel />
      <p className="mb-2 text-xs text-neutral-500">
        全体設定。新規プロジェクトの既定値になります(プロジェクト単位で上書き可能)。
      </p>
      <SaveBar
        dirty={dirty}
        saving={update.isPending}
        saved={update.isSuccess}
        error={update.isError ? update.error : null}
        onSave={() => update.mutate(draft)}
        onDiscard={() => {
          setDraft({})
          update.reset()  // 「保存しました」表示を消す
        }}
      />
      <SettingsFields
        values={{ ...settings.data.values, ...draft }}
        meta={settings.data}
        onSet={(key, value) => setDraft((d) => ({ ...d, [key]: value }))}
      />
    </div>
  )
}
