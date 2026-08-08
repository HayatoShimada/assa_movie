/**
 * プロジェクト設定の編集パネル。
 *
 * projects.settings_json(グローバルとの差分)を編集する。
 * 各項目の「既定に戻す」で差分から外れ、以後はグローバル設定に追従する。
 * 変更は下書きに溜め、保存ボタンでまとめて反映する。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Project } from '../../api/client'
import { TEMPLATES, templateFor } from '../../lib/catalogs'
import { overrideProps, type SettingsValues } from '../../lib/settings'
import { SaveBar } from '../settings/SaveBar'
import { SettingsFields } from '../settings/SettingsFields'
import { selectCls } from '../ui'

export function ProjectSettingsPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  // 保存前の差分。nullなら未編集(サーバー側の値をそのまま表示する)
  const [draft, setDraft] = useState<SettingsValues | null>(null)
  const update = useMutation({
    mutationFn: (patch: Parameters<typeof api.updateProject>[1]) =>
      api.updateProject(project.id, patch),
    onSuccess: () => {
      setDraft(null)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      // エディタのプレビューは ['project', id] を見るので、これも更新しないと
      // 字幕スタイルの変更が反映されない
      queryClient.invalidateQueries({ queryKey: ['project', project.id] })
    },
  })

  if (!settings.data) return null
  const saved = (project.settings ?? {}) as SettingsValues
  const overrides = draft ?? saved
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(saved)

  return (
    <div className="mt-3 rounded border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs text-neutral-500">テンプレート</span>
        <select
          data-testid={`project-template-${project.id}`}
          className={selectCls}
          value={templateFor(project)?.id ?? TEMPLATES[0].id}
          onChange={(e) => {
            // テンプレートは項目数が少なく取り違えも起きにくいので即時保存する
            const t = TEMPLATES.find((t) => t.id === e.target.value)
            if (t) update.mutate({ input_orientation: t.input, output_orientation: t.output })
          }}
        >
          {TEMPLATES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
      <SaveBar
        testId={`project-settings-save-${project.id}`}
        dirty={dirty}
        saving={update.isPending}
        saved={update.isSuccess}
        error={update.isError ? update.error : null}
        onSave={() => update.mutate({ settings: overrides })}
        onDiscard={() => {
          setDraft(null)
          update.reset()  // 「保存しました」表示を消す
        }}
      />
      <SettingsFields
        idPrefix={`project-${project.id}`}
        meta={settings.data}
        {...overrideProps(settings.data.values, overrides, setDraft)}
      />
    </div>
  )
}
