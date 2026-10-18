/**
 * 整形の設定(フィラー排除・指示語置換)。
 *
 * どちらも「文字起こしの結果をどう読みやすくするか」なので同じ区分にまとめる。
 * 指示語置換の実行はレビュータブのボタンで始まる(ここは既定値)。
 * どれも既定のままで使えるので、すべて「詳しい設定」に置く。
 */
import { HelpTip } from '../../HelpTip'
import { selectCls } from '../../ui'
import { Row, Section, showTier, type SectionProps } from './common'

export function TextSection(props: SectionProps) {
  const { values: v, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  if (!showTier(props, 'advanced')) return null

  return (
    <Section title="整形">
      <Row
        label={
          <>
            フィラー排除
            <HelpTip term="フィラー" />
          </>
        }
        hint="「えー」「あのー」などを字幕から取り除くかどうか。"
      >
        <select
          data-testid={`${idPrefix}-filler-level`}
          className={selectCls}
          value={String(v.filler_level)}
          onChange={(e) => set('filler_level')(e.target.value)}
        >
          <option value="off">無効(言い淀みも残す)</option>
          <option value="weak">弱(明らかな言い淀みのみ)</option>
          <option value="strong">強(曖昧なものはAIが判定し、迷えば質問)</option>
        </select>
      </Row>
      <Row
        label={
          <>
            指示語置換の積極性
            <HelpTip term="指示語" />
          </>
        }
        hint="レビュータブの「指示語を解決」で、どこまでの言葉を対象にするか。"
      >
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
      <Row label="指示語置換の表現形式" hint="指す先を字幕にどう書き足すか。注釈なら発言そのものは変えません。">
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
      <Row
        label="指示語置換の適用モード"
        hint="AIの提案をそのまま字幕に反映するか、レビュータブで確認してから反映するか。"
      >
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
