/**
 * 設定フォームの共有フィールド群。
 *
 * グローバル設定タブ(SettingsForm)とプロジェクト設定(作成ダイアログ・編集パネル)の
 * 両方から使う。値の保存先はonSetに委ねる。プロジェクトモードでは
 * overriddenKeys/onResetで「既定に戻す」を出す。
 *
 * 項目は「基本」と、折りたたんだ「詳しい設定」に分けて出す(sections/common.tsx)。
 * 中身は意味ごとのセクション(sections/配下)に分かれている。
 * どのセクションを出すかは画面ごとに選べる(sections プロパティ)。
 * 実行環境まわり(どのエンジンで動かすか)はここには無い。初回検出で確定し、
 * 設定タブの「実行環境」パネルが表示と再検出を担当する。
 */
import { LayoutSection } from './sections/LayoutSection'
import { LlmSection } from './sections/LlmSection'
import { SubtitleSection } from './sections/SubtitleSection'
import { TextSection } from './sections/TextSection'
import { TranscriptionSection } from './sections/TranscriptionSection'
import type { SectionMeta, SectionProps, SettingsTier } from './sections/common'

export type { SectionMeta }

/** 「詳しい設定」に項目を持つセクション(各セクションの showTier と対応) */
const ADVANCED_SECTIONS = new Set<string>(['transcription', 'text', 'subtitle'])

/** 表示順はこの並び(意味の近いものを隣に置く) */
const SECTIONS = {
  transcription: TranscriptionSection,
  text: TextSection,
  subtitle: SubtitleSection,
  layout: LayoutSection,
  llm: LlmSection,
} as const

export type SectionName = keyof typeof SECTIONS

const ALL_SECTIONS = Object.keys(SECTIONS) as SectionName[]

export function SettingsFields({
  values,
  meta,
  onSet,
  idPrefix = 'setting',
  overriddenKeys,
  onReset,
  sections = ALL_SECTIONS,
}: {
  values: Record<string, unknown>
  meta: SectionMeta
  onSet: (key: string, value: unknown) => void
  idPrefix?: string
  /** プロジェクトモード: グローバルと異なるキー(「既定に戻す」を表示) */
  overriddenKeys?: Set<string>
  onReset?: (key: string) => void
  /** 出すセクション(既定は全部) */
  sections?: SectionName[]
}) {
  const props: SectionProps = { values, meta, onSet, idPrefix, overriddenKeys, onReset }
  const shown = ALL_SECTIONS.filter((name) => sections.includes(name))
  const render = (tier: SettingsTier) =>
    shown.map((name) => {
      const Component = SECTIONS[name]
      return <Component key={name} {...props} tier={tier} />
    })
  // 詳しい設定に属する項目を出すセクションがあるときだけ折りたたみを置く
  const hasAdvanced = shown.some((name) => ADVANCED_SECTIONS.has(name))

  return (
    <div>
      <div
        data-testid={`${idPrefix}-basic`}
        className="divide-y divide-neutral-100 dark:divide-neutral-800"
      >
        {render('basic')}
      </div>
      {hasAdvanced && (
        <details
          data-testid={`${idPrefix}-advanced`}
          className="mt-2 rounded-md border border-neutral-200 px-3 py-1 dark:border-neutral-800"
        >
          <summary className="cursor-pointer py-1 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
            詳しい設定
            <span className="ml-2 text-xs font-normal text-neutral-500">
              文字起こしモデル・指示語やフィラーの扱い・字幕の細かい調整(ふつうは既定のままで大丈夫です)
            </span>
          </summary>
          <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {render('advanced')}
          </div>
        </details>
      )}
    </div>
  )
}
