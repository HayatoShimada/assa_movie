/**
 * AIが使えない設定のときに、ホーム/編集画面の上に出す警告と直し方。
 *
 * 評価で、既定の Ollama モデル(qwen3:32b)が入っていない機体だと、
 * 切り抜き候補・AIに指示・指示語の解決・固有名詞スキャンを押すたびに
 * 「Ollama呼び出しに3回失敗: 404」で失敗するまで気付けなかった。
 * 押す前に GET /api/llm/status で調べ、その場で直せるようにする:
 * - おすすめのモデルに切り替える / インストール済みのモデルから選ぶ
 * - 使い続けたいなら `ollama pull <名前>` を実行して「もう一度確かめる」
 * - Ollama 未起動なら起動して「もう一度確かめる」
 * - クラウドのキー未登録ならその場で登録
 *
 * 実行時に黙って別のモデルへ切り替えることはしない(直すのは利用者の操作だけ)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorText } from '../../api/client'
import { Button, selectCls } from '../ui'
import { CloudKeySetup } from './ApiKeysPanel'

export function LlmStatusBanner({
  projectId,
  className = 'mb-4',
}: {
  projectId?: number | null
  /** 置き場所ごとの余白(問題が無いときは何も描かないので、外側に枠を作らない) */
  className?: string
}) {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const keys = useQuery({ queryKey: ['keys'], queryFn: api.getApiKeys })
  const project = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(projectId!),
    enabled: projectId != null,
  })
  const v = settings.data?.values
  // 設定・キー・プロジェクトの上書きが変わったら調べ直す(どこで直しても追従する)
  const status = useQuery({
    queryKey: [
      'llm-status',
      projectId ?? null,
      v?.llm_provider,
      v?.ollama_model,
      v?.gemini_model,
      v?.claude_model,
      JSON.stringify(keys.data ?? {}),
      JSON.stringify(project.data?.settings ?? {}),
    ],
    queryFn: () => api.getLlmStatus(projectId ?? undefined),
    enabled: settings.isSuccess,
  })
  const apply = useMutation({
    mutationFn: (model: string) =>
      api.updateSettings({ llm_provider: 'ollama', ollama_model: model }),
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
  })

  const s = status.data
  if (!s || s.ok) return null
  const canFixHere = !s.overridden_by_project

  return (
    <div
      role="alert"
      data-testid="llm-status-banner"
      data-code={s.code ?? undefined}
      className={`${className} space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200`}
    >
      <p data-testid="llm-status-message" className="font-medium">
        {s.message}
      </p>

      {s.overridden_by_project && (
        <p className="text-xs">
          このプロジェクトの設定でAIを指定しています。ホームのプロジェクトの「設定」から変更してください。
        </p>
      )}

      {canFixHere && s.code === 'model_not_installed' && (
        <div className="flex flex-wrap items-center gap-2">
          {s.recommended_model && (
            <Button
              data-testid="llm-apply-recommended"
              type="button"
              disabled={apply.isPending}
              onClick={() => apply.mutate(s.recommended_model!)}
            >
              おすすめの「{s.recommended_model}」に切り替える
            </Button>
          )}
          {s.installed_models.length > 0 && (
            <label className="flex items-center gap-1 text-xs">
              インストール済みから選ぶ:
              <select
                data-testid="llm-pick-model"
                className={selectCls}
                value=""
                onChange={(e) => e.target.value && apply.mutate(e.target.value)}
                disabled={apply.isPending}
              >
                <option value="">選んでください</option>
                {s.installed_models.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      {s.pull_command && (
        <p className="text-xs">
          「{s.model}」を使い続ける場合は、ターミナルで{' '}
          <code
            data-testid="llm-pull-command"
            className="select-all rounded bg-white/70 px-1 font-mono dark:bg-black/30"
          >
            {s.pull_command}
          </code>{' '}
          を実行してから「もう一度確かめる」を押してください。
        </p>
      )}

      {canFixHere && s.code === 'no_key' && (
        <CloudKeySetup providers={[s.provider]} selected={s.provider} />
      )}

      {s.code !== 'no_key' && (
        <Button
          data-testid="llm-recheck"
          type="button"
          variant="ghost"
          disabled={status.isFetching}
          onClick={() => status.refetch()}
        >
          {status.isFetching ? '確かめています…' : 'もう一度確かめる'}
        </Button>
      )}
      {apply.isError && <p className="text-xs text-red-600">{errorText(apply.error)}</p>}
    </div>
  )
}
