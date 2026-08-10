/**
 * 設定フォームの共有フィールド群。
 *
 * グローバル設定タブ(SettingsForm)とプロジェクト設定(作成ダイアログ・編集パネル)の
 * 両方から使う。値の保存先はonSetに委ねる。プロジェクトモードでは
 * overriddenKeys/onResetで「既定に戻す」を出す。
 *
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
import type { SectionMeta, SectionProps } from './sections/common'

export type { SectionMeta }

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
  return (
    <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
      {ALL_SECTIONS.filter((name) => sections.includes(name)).map((name) => {
        const Component = SECTIONS[name]
        return <Component key={name} {...props} />
      })}
    </div>
  )
}
