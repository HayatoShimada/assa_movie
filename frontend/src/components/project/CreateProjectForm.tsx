/**
 * プロジェクト作成フォーム。
 *
 * テンプレート(入力の向き→出力の向き)を4択カードで選び、
 * 詳細設定はグローバル設定をプリフィルして差分だけをsettingsとして送る。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Orientation } from '../../api/client'
import { TEMPLATES, type Template } from '../../lib/catalogs'
import { overrideProps, type SettingsValues } from '../../lib/settings'
import { Button } from '../ui'
import { SettingsFields } from '../settings/SettingsFields'

function OrientationIcon({ orientation }: { orientation: Orientation }) {
  // 矩形1つで向きを表す(横=16:9、縦=9:16)
  return orientation === 'landscape' ? (
    <rect x="1" y="7" width="22" height="13" rx="2" />
  ) : (
    <rect x="6.5" y="1" width="11" height="22" rx="2" />
  )
}

function TemplateIcon({ input, output }: { input: Orientation; output: Orientation }) {
  return (
    <span className="flex items-center gap-1">
      <svg width="24" height="24" viewBox="0 0 24 24" className="fill-none stroke-current" strokeWidth="2">
        <OrientationIcon orientation={input} />
      </svg>
      <svg width="14" height="14" viewBox="0 0 14 14" className="stroke-current" strokeWidth="2">
        <path d="M1 7h10m0 0L8 4m3 3-3 3" fill="none" />
      </svg>
      <svg width="24" height="24" viewBox="0 0 24 24" className="fill-current opacity-80 stroke-current" strokeWidth="1">
        <OrientationIcon orientation={output} />
      </svg>
    </span>
  )
}

export function CreateProjectForm() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const [name, setName] = useState('')
  const [template, setTemplate] = useState<Template>(TEMPLATES[0])
  const [showDetails, setShowDetails] = useState(false)
  // グローバル設定との差分だけを保持する
  const [overrides, setOverrides] = useState<SettingsValues>({})

  const create = useMutation({
    mutationFn: () =>
      api.createProject({
        name,
        input_orientation: template.input,
        output_orientation: template.output,
        settings: overrides,
      }),
    onSuccess: () => {
      setName('')
      setOverrides({})
      setShowDetails(false)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  return (
    <form
      className="space-y-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-800"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim()) create.mutate()
      }}
    >
      <div className="flex gap-2">
        <input
          data-testid="new-project-name"
          className="flex-1 rounded-md border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="新しいプロジェクト名"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button data-testid="create-project" type="submit" disabled={create.isPending}>
          作成
        </Button>
      </div>

      <div>
        <p className="mb-1 text-xs text-neutral-500">テンプレート(元動画の向き → 書き出しの向き)</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {TEMPLATES.map((t) => (
            <button
              key={t.id}
              type="button"
              data-testid={`template-${t.id}`}
              onClick={() => setTemplate(t)}
              className={`flex flex-col items-center gap-1 rounded-md border p-2 text-xs ${
                template.id === t.id
                  ? 'border-blue-600 bg-blue-50 font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300'
                  : 'border-neutral-300 text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-900'
              }`}
            >
              <TemplateIcon input={t.input} output={t.output} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <button
          type="button"
          data-testid="toggle-project-settings"
          className="text-xs text-blue-600 hover:underline"
          onClick={() => setShowDetails((s) => !s)}
        >
          {showDetails ? '▼ 詳細設定を閉じる' : '▶ 詳細設定(全体設定から変更する項目だけ保存)'}
        </button>
        {showDetails && settings.data && (
          <div className="mt-2 max-h-96 overflow-y-auto rounded border border-neutral-200 p-3 dark:border-neutral-800">
            <SettingsFields
              idPrefix="new-project"
              meta={settings.data}
              {...overrideProps(settings.data.values, overrides, setOverrides)}
            />
          </div>
        )}
      </div>

      {create.isError && (
        <p className="text-xs text-red-600">作成に失敗しました: {String(create.error.message)}</p>
      )}
    </form>
  )
}
