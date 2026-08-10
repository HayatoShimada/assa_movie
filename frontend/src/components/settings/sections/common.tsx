/**
 * 設定セクションの共通部品。
 *
 * 各セクション(文字起こし・整形・字幕・LLM…)は同じpropsを受け取り、
 * どの画面(グローバル設定/プロジェクト設定/新規作成)からでも使える。
 */
import type { SettingsResponse } from '../../../api/client'

/** セクションが必要とするメタ情報(バックエンドの /api/settings 由来) */
export type SectionMeta = Pick<
  SettingsResponse,
  'asr_models' | 'diarization_ready' | 'llm_providers'
>

export interface SectionProps {
  values: Record<string, unknown>
  meta: SectionMeta
  onSet: (key: string, value: unknown) => void
  idPrefix: string
  /** プロジェクトモード: グローバルと異なるキー(「既定に戻す」を表示) */
  overriddenKeys?: Set<string>
  onReset?: (key: string) => void
}

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-neutral-600 dark:text-neutral-400">{label}</span>
      {children}
    </label>
  )
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="py-2">
      <h3 className="mb-1 text-sm font-semibold">{title}</h3>
      {children}
    </div>
  )
}

/** 「既定に戻す」ボタン(プロジェクトモードで上書き中の項目にだけ出る) */
export function resetButton(props: SectionProps, key: string) {
  if (!props.overriddenKeys?.has(key) || !props.onReset) return null
  const onReset = props.onReset
  return (
    <button
      type="button"
      className="ml-1 text-xs text-blue-600 hover:underline"
      onClick={() => onReset(key)}
    >
      既定に戻す
    </button>
  )
}
