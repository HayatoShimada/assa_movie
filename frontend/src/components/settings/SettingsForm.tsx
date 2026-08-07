/** 設定タブ(グローバル設定)。GET/PATCH /api/settings と双方向バインドする。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { EnvironmentPanel } from './EnvironmentPanel'
import { SettingsFields } from './SettingsFields'

export function SettingsForm() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const update = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
  })

  if (settings.isPending) return <p className="p-4 text-sm text-neutral-500">読み込み中...</p>
  if (settings.isError) return <p className="p-4 text-sm text-red-600">設定を取得できません</p>

  return (
    <div className="p-4">
      <EnvironmentPanel />
      <p className="mb-2 text-xs text-neutral-500">
        全体設定。新規プロジェクトの既定値になります(プロジェクト単位で上書き可能)。
      </p>
      <SettingsFields
        values={settings.data.values}
        meta={settings.data}
        onSet={(key, value) => update.mutate({ [key]: value })}
      />
      {update.isError && (
        <p className="pt-2 text-xs text-red-600">保存に失敗しました: {String(update.error)}</p>
      )}
    </div>
  )
}
