/** 設定タブ。GET/PATCH /api/settings と双方向バインドする。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-neutral-600 dark:text-neutral-400">{label}</span>
      {children}
    </label>
  )
}

const selectCls =
  'rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900'

export function SettingsForm() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const update = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
  })

  if (settings.isPending) return <p className="p-4 text-sm text-neutral-500">読み込み中...</p>
  if (settings.isError) return <p className="p-4 text-sm text-red-600">設定を取得できません</p>

  const v = settings.data.values
  const set = (key: string) => (value: unknown) => update.mutate({ [key]: value })

  const asrNote = settings.data.asr_models.find((m) => m.id === v.asr_model)?.note

  return (
    <div className="divide-y divide-neutral-100 p-4 dark:divide-neutral-800">
      <div className="pb-2">
        <h3 className="mb-1 text-sm font-semibold">文字起こし</h3>
        <Row label="ASRモデル">
          <select
            data-testid="setting-asr-model"
            className={selectCls}
            value={String(v.asr_model)}
            onChange={(e) => set('asr_model')(e.target.value)}
          >
            {settings.data.asr_models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </Row>
        {asrNote && <p className="text-xs text-neutral-500">{asrNote}</p>}
        <Row label="話者分離">
          <input
            type="checkbox"
            checked={Boolean(v.diarization_enabled)}
            onChange={(e) => set('diarization_enabled')(e.target.checked)}
          />
        </Row>
        <Row label="男性話者の表示名">
          <input
            className={selectCls}
            defaultValue={String(v.male_name)}
            onBlur={(e) => e.target.value !== v.male_name && set('male_name')(e.target.value)}
          />
        </Row>
        <Row label="女性話者の表示名">
          <input
            className={selectCls}
            defaultValue={String(v.female_name)}
            onBlur={(e) => e.target.value !== v.female_name && set('female_name')(e.target.value)}
          />
        </Row>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">指示語置換</h3>
        <Row label="有効">
          <input
            type="checkbox"
            checked={Boolean(v.pronoun_enabled)}
            onChange={(e) => set('pronoun_enabled')(e.target.checked)}
          />
        </Row>
        <Row label="積極性">
          <select
            className={selectCls}
            value={String(v.pronoun_level)}
            onChange={(e) => set('pronoun_level')(e.target.value)}
          >
            <option value="weak">弱(これ・それ・あれのみ)</option>
            <option value="medium">中(推奨)</option>
            <option value="strong">強(そういう系も対象)</option>
          </select>
        </Row>
        <Row label="表現形式">
          <select
            data-testid="setting-pronoun-form"
            className={selectCls}
            value={String(v.pronoun_form)}
            onChange={(e) => set('pronoun_form')(e.target.value)}
          >
            <option value="annotate">注釈: それ(去年のハッカソン)(推奨)</option>
            <option value="replace">置換: 去年のハッカソン</option>
            <option value="complete">補完(全件レビュー必須)</option>
          </select>
        </Row>
        <Row label="適用モード">
          <select
            className={selectCls}
            value={String(v.pronoun_apply_mode)}
            onChange={(e) => set('pronoun_apply_mode')(e.target.value)}
          >
            <option value="full_auto">全自動</option>
            <option value="auto_and_review">確実なものは自動、迷いはレビュー(推奨)</option>
            <option value="all_review">全件レビュー</option>
          </select>
        </Row>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">字幕</h3>
        <Row label="字幕モード">
          <select
            data-testid="setting-subtitle-mode"
            className={selectCls}
            value={String(v.subtitle_mode)}
            onChange={(e) => set('subtitle_mode')(e.target.value)}
          >
            <option value="all">全文字幕(全セグメントを表示)</option>
            <option value="selective">選択字幕(必要なものだけ)</option>
          </select>
        </Row>
        {v.subtitle_mode === 'selective' && (
          <Row label={`採用率 ${Math.round(Number(v.subtitle_adoption_rate) * 100)}%`}>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              defaultValue={Number(v.subtitle_adoption_rate)}
              onMouseUp={(e) =>
                set('subtitle_adoption_rate')(Number((e.target as HTMLInputElement).value))
              }
            />
          </Row>
        )}
        <Row label={`字幕サイズ: ${v.subtitle_font_size}px`}>
          <input
            data-testid="setting-subtitle-font-size"
            type="range"
            min={24}
            max={72}
            step={1}
            defaultValue={Number(v.subtitle_font_size ?? 48)}
            onMouseUp={(e) =>
              set('subtitle_font_size')(Number((e.target as HTMLInputElement).value))
            }
          />
        </Row>
        <Row label={`1行の最大文字数: ${v.subtitle_max_chars_per_line}`}>
          <input
            type="range"
            min={10}
            max={20}
            defaultValue={Number(v.subtitle_max_chars_per_line)}
            onMouseUp={(e) =>
              set('subtitle_max_chars_per_line')(Number((e.target as HTMLInputElement).value))
            }
          />
        </Row>
        <Row label="フィラー排除">
          <select
            data-testid="setting-filler-level"
            className={selectCls}
            value={String(v.filler_level)}
            onChange={(e) => set('filler_level')(e.target.value)}
          >
            <option value="off">無効(言い淀みも残す)</option>
            <option value="weak">弱(明らかな言い淀みのみ)</option>
            <option value="strong">強(曖昧なものはLLM判定+質問)</option>
          </select>
        </Row>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">LLM</h3>
        <Row label="プロバイダ">
          <select
            data-testid="setting-llm-provider"
            className={selectCls}
            value={String(v.llm_provider)}
            onChange={(e) => set('llm_provider')(e.target.value)}
          >
            {settings.data.llm_providers.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.ready}>
                {p.label}
                {!p.ready ? '(APIキー未設定)' : ''}
              </option>
            ))}
          </select>
        </Row>
        <p className="text-xs text-neutral-500">
          {settings.data.llm_providers.find((p) => p.id === v.llm_provider)?.note}
        </p>
      </div>

      {update.isError && (
        <p className="pt-2 text-xs text-red-600">保存に失敗しました: {String(update.error)}</p>
      )}
    </div>
  )
}
