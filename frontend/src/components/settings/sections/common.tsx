/**
 * 設定セクションの共通部品。
 *
 * 各セクション(文字起こし・整形・字幕・AI…)は同じpropsを受け取り、
 * どの画面(グローバル設定/プロジェクト設定/新規作成)からでも使える。
 *
 * 項目は「基本」(話者名・字幕の見た目・AIの選択など、初めての人も触るもの)と
 * 「詳しい設定」(文字起こしモデル・指示語置換の細かい挙動など)に分ける。
 * 以前は専門用語の項目が説明なしで一列に並び、初めての人がどこを触ればいいか
 * 分からなかった(評価での指摘)。各項目には1行の説明(hint)を付ける。
 */
import type { SettingsResponse } from '../../../api/client'

/** セクションが必要とするメタ情報(バックエンドの /api/settings 由来) */
export type SectionMeta = Pick<
  SettingsResponse,
  'asr_models' | 'diarization_ready' | 'llm_providers'
>

/** 基本 / 詳しい設定。未指定なら両方出す */
export type SettingsTier = 'basic' | 'advanced'

export interface SectionProps {
  values: Record<string, unknown>
  meta: SectionMeta
  onSet: (key: string, value: unknown) => void
  idPrefix: string
  /** プロジェクトモード: グローバルと異なるキー(「既定に戻す」を表示) */
  overriddenKeys?: Set<string>
  onReset?: (key: string) => void
  /** 出す項目の区分(未指定なら全部) */
  tier?: SettingsTier
}

/** この区分の項目を出すか */
export function showTier(props: Pick<SectionProps, 'tier'>, tier: SettingsTier): boolean {
  return props.tier === undefined || props.tier === tier
}

export function Row({
  label,
  hint,
  children,
}: {
  label: React.ReactNode
  /** 1行の説明(専門用語を使わずに、何が変わるかを書く) */
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="min-w-0">
        <span className="text-neutral-700 dark:text-neutral-300">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-neutral-500">{hint}</span>}
      </span>
      <span className="shrink-0">{children}</span>
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
