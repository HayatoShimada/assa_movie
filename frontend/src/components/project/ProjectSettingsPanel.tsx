/**
 * プロジェクト設定の編集パネル。
 *
 * projects.settings_json(グローバルとの差分)を編集する。
 * 各項目の「既定に戻す」で差分から外れ、以後はグローバル設定に追従する。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Orientation, type Project } from '../../api/client'
import { SettingsFields } from '../settings/SettingsFields'
import { TEMPLATES } from './CreateProjectForm'

export function ProjectSettingsPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const update = useMutation({
    mutationFn: (patch: Parameters<typeof api.updateProject>[1]) =>
      api.updateProject(project.id, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
  })

  if (!settings.data) return null
  const overrides = (project.settings ?? {}) as Record<string, unknown>
  const mergedValues = { ...settings.data.values, ...overrides }
  const templateId =
    TEMPLATES.find(
      (t) => t.input === project.input_orientation && t.output === project.output_orientation,
    )?.id ?? 'l2l'

  return (
    <div className="mt-3 rounded border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs text-neutral-500">テンプレート</span>
        <select
          data-testid={`project-template-${project.id}`}
          className="rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          value={templateId}
          onChange={(e) => {
            const t = TEMPLATES.find((t) => t.id === e.target.value)
            if (t)
              update.mutate({
                input_orientation: t.input as Orientation,
                output_orientation: t.output as Orientation,
              })
          }}
        >
          {TEMPLATES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      <SettingsFields
        idPrefix={`project-${project.id}`}
        values={mergedValues}
        meta={settings.data}
        onSet={(key, value) => update.mutate({ settings: { ...overrides, [key]: value } })}
        overriddenKeys={new Set(Object.keys(overrides))}
        onReset={(key) => {
          const next = { ...overrides }
          delete next[key]
          update.mutate({ settings: next })
        }}
      />
      {update.isError && (
        <p className="pt-2 text-xs text-red-600">保存に失敗しました: {String(update.error)}</p>
      )}
    </div>
  )
}
