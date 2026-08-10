/**
 * 整形の設定(フィラー排除・指示語置換)。
 *
 * どちらも「文字起こしの結果をどう読みやすくするか」なので同じ区分にまとめる。
 * 指示語置換の実行はレビュータブのボタンで始まる(ここは既定値)。
 */
import { selectCls } from '../../ui'
import { Row, Section, type SectionProps } from './common'

export function TextSection({ values: v, onSet, idPrefix }: SectionProps) {
  const set = (key: string) => (value: unknown) => onSet(key, value)

  return (
    <Section title="整形">
      <Row label="フィラー排除">
        <select
          data-testid={`${idPrefix}-filler-level`}
          className={selectCls}
          value={String(v.filler_level)}
          onChange={(e) => set('filler_level')(e.target.value)}
        >
          <option value="off">無効(言い淀みも残す)</option>
          <option value="weak">弱(明らかな言い淀みのみ)</option>
          <option value="strong">強(曖昧なものはLLM判定+質問)</option>
        </select>
      </Row>
      <Row label="指示語置換の積極性">
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
      <Row label="指示語置換の表現形式">
        <select
          data-testid={`${idPrefix}-pronoun-form`}
          className={selectCls}
          value={String(v.pronoun_form)}
          onChange={(e) => set('pronoun_form')(e.target.value)}
        >
          <option value="annotate">注釈: それ(先月のイベント)(推奨)</option>
          <option value="replace">置換: 先月のイベント</option>
          <option value="complete">補完(全件レビュー必須)</option>
        </select>
      </Row>
      <Row label="指示語置換の適用モード">
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
    </Section>
  )
}
