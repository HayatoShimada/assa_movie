/**
 * 設定タブ(グローバル設定)。
 *
 * 変更はいったん下書きに溜め、保存ボタンでまとめて PATCH /api/settings する。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import type { SettingsValues } from '../../lib/settings'
import { ApiKeysPanel } from './ApiKeysPanel'
import { SetupPanel } from './SetupPanel'
import { EnvironmentPanel } from './EnvironmentPanel'
import { LicensePanel } from './LicensePanel'
import { OpenSourcePanel } from './OpenSourcePanel'
import { SaveBar } from './SaveBar'
import { SettingsFields } from './SettingsFields'
import { Button } from '../ui'

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
  // 未完了に戻すとAppがウィザードを出す(この画面の上に重なる)
  const rerunSetup = useMutation({
    mutationFn: () => api.updateSettings({ setup_completed: false }),
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
  })

  if (settings.isPending) return <p className="p-4 text-sm text-neutral-500">読み込み中...</p>
  if (settings.isError) return <p className="p-4 text-sm text-red-600">設定を取得できません</p>

  const dirty = Object.keys(draft).length > 0

  return (
    <div className="p-4">
      {/* 上から「この端末の状態」→「全体設定」の順。まず動く状態かを示す */}
      <EnvironmentPanel />
      <SetupPanel />
      <LicensePanel />
      <ApiKeysPanel />
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
      <section
        data-testid="rerun-setup-panel"
        className="mb-4 mt-4 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
      >
        <h3 className="mb-1 text-sm font-semibold">はじめの設定</h3>
        <p className="mb-2 text-xs text-neutral-500">
          環境の確認・使うAIの選択・モデルの取得を、もう一度順に案内します。
        </p>
        <Button
          data-testid="rerun-setup"
          type="button"
          onClick={() => rerunSetup.mutate()}
          disabled={rerunSetup.isPending}
        >
          やり直す
        </Button>
      </section>
      {/* 設定項目ではなく参照情報なので最後に置く */}
      <OpenSourcePanel />
    </div>
  )
}
